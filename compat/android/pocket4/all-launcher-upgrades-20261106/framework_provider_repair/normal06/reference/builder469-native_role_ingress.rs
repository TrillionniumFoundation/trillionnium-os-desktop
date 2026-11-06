//! Complete framework Java and Android JNI build for the disabled typed ingress.
//!
//! This entry uses the normal package/source locks, strict dependency mode and
//! reversible source-projection journal. A successful build command is not a
//! runtime authorization, installation, or qualification of its linked output.
use crate::util::*;
use serde::Serialize;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::fs::{self, Metadata, OpenOptions};
use std::io::{Read, Write};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::path::{Component, Path, PathBuf};

pub const TARGETS: &[&str] = &["framework-minus-apex", "libandroid_runtime"];
const ORIGINAL_LOCK: &str = "android/manifest/m2-sparse-source-lock.json";
const PREVIOUS_SOURCE_LOCK: &str = "android/manifest/m2-role-ingress-source-lock.json";
const PREVIOUS_PROVIDER_LOCK: &str = "android/manifest/m2-role-ingress-provider-source-lock.json";
const SOURCE_LOCK: &str = "android/manifest/m2-role-ingress-provider2-source-lock.json";
const ORIGINAL_LOCK_BYTES: usize = 84522;
const ORIGINAL_LOCK_SHA: &str =
    "4d8f2d047254268305f4802d9dd67bebdfd162d836664c733ecc07e2f9ced178";
// Derived from the three observed fixed-commit root trees. Structural extension
// checks alone cannot prove that an appended directory was actually observed.
const PREVIOUS_SOURCE_LOCK_BYTES: usize = 86293;
const PREVIOUS_SOURCE_LOCK_SHA: &str =
    "ca62c69ff22eba9ff84992aaa18114b74c951802c084bd8cb25cfc22d741ae54";
// Preserve the compiled provider1 lock and validate the two newly observed
// native providers as an exact monotonic successor at the same superproject.
const PREVIOUS_PROVIDER_LOCK_BYTES: usize = 96322;
const PREVIOUS_PROVIDER_LOCK_SHA: &str = "5c28f77e998cb75fd04de121e43a36fc3d8515c18249930268a2ffb6e5e372f7";
const SOURCE_LOCK_BYTES: usize = 96957;
const SOURCE_LOCK_SHA: &str = "72848909e4931d712a3d59f344904ae8642b32c35a01cf520a51afce4c56b50d";
const CAR_NATIVE_EXTENSIONS: &[&str] = &[
    "cpp/vhal/client/include",
    "cpp/vhal/client/src",
    "cpp/car_binder_lib/largeParcelable/include",
];
const NEURALNETWORKS_ADDITION_JSON: &str = r#"{"path":"packages/modules/NeuralNetworks","name":"platform/packages/modules/NeuralNetworks","commit":"a44a9032ab9a8438c0e13aca765d6ee4edebba2c","purpose":"Exact Android 17 superproject NNAPI utility defaults and complete native type providers required by the existing hardware interface consumers","sparse_paths":["common/types/include","common/types/operations/include","common/types/operations/src","common/types/src"]}"#;
const PROVIDER_EXTENSIONS: &[(&str, &[&str])] = &[
    ("platform_testing", &["libraries/motion/src", "libraries/motion/compose/src", "libraries/motion/compose/values/src", "libraries/screenshot/src/main", "libraries/screenshot/proto", "libraries/uiautomator-helpers/src", "libraries/runner/src/main/java", "libraries/device-collectors/src/main/java", "libraries/collectors-helper/adservices/src", "libraries/collectors-helper/app/src", "libraries/collectors-helper/generic/src", "libraries/collectors-helper/jank/src", "libraries/collectors-helper/lyric/src", "libraries/collectors-helper/memory/src", "libraries/collectors-helper/perfetto/src", "libraries/collectors-helper/power/src", "libraries/collectors-helper/simpleperf/src", "libraries/collectors-helper/system/src", "libraries/collectors-helper/utilities/src", "libraries/junitxml/src"]),
    ("prebuilts/sdk", &["current/androidx", "18/public", "current/multidex", "current/test", "current/support/v7/appcompat/res", "current/support/manifests/android-support-v7-appcompat"]),
    ("prebuilts/misc", &["common/ub-uiautomator", "common/robolectric-native-prebuilt", "common/robolectric/android-all"]),
    ("external/ow2-asm", &["asm/src/main", "asm-analysis/src/main", "asm-commons/src/main", "asm-tree/src/main", "asm-util/src/main"]),
    ("external/icu", &["icu4j/main"]),
    ("prebuilts/tools", &["common/m2/repository/com/almworks/sqlite4java/libsqlite4java-linux-amd64/0.282", "common/m2/repository/com/almworks/sqlite4java/libsqlite4java-linux-i386/0.282", "common/m2/repository/com/almworks/sqlite4java/libsqlite4java-osx/0.282", "common/m2/repository/com/almworks/sqlite4java/sqlite4java-win32-x64/0.282", "common/m2/repository/com/almworks/sqlite4java/sqlite4java-win32-x86/0.282", "common/m2/repository/com/almworks/sqlite4java/sqlite4java/0.282", "common/m2/repository/com/android/support/test/monitor/1.0.2-alpha1", "common/m2/repository/com/google/android/apps/common/testing/accessibility/framework/accessibility-test-framework/2.0", "common/m2/repository/com/google/android/apps/common/testing/accessibility/framework/accessibility-test-framework/2.1", "common/m2/repository/com/google/dagger/dagger-compiler/2.7", "common/m2/repository/com/google/dagger/dagger-producers/2.7", "common/m2/repository/com/google/dagger/dagger/2.7", "common/m2/repository/com/google/devtools/ksp/symbol-processing-api/1.4.10-dev-experimental-20201110", "common/m2/repository/com/google/guava/guava/23.0", "common/m2/repository/com/google/guava/guava/listenablefuture/1.0", "common/m2/repository/com/google/http-client/google-http-client-jackson2/1.28.0", "common/m2/repository/com/google/inject/guice/3.0", "common/m2/repository/com/google/j2objc/j2objc-annotations/1.1", "common/m2/repository/com/google/testing/compile/compile-testing/0.19", "common/m2/repository/com/intellij/core-analysis", "common/m2/repository/com/sampullara/cli/1.1.2", "common/m2/repository/com/squareup/kotlinpoet/1.8.0", "common/m2/repository/com/squareup/okhttp/okhttp/2.7.4", "common/m2/repository/com/squareup/okhttp4/okhttp/4.0.0", "common/m2/repository/com/squareup/okio/okio/1.9.0", "common/m2/repository/com/squareup/wire/wire-runtime-jvm/4.7.0", "common/m2/repository/com/thoughtworks/xstream/xstream/1.4.8", "common/m2/repository/commons-codec/commons-codec/1.10", "common/m2/repository/commons-io/commons-io/2.4", "common/m2/repository/io/grpc/grpc-all/1.0.3", "common/m2/repository/io/grpc/grpc-context/1.0.3", "common/m2/repository/io/grpc/grpc-core/1.0.3", "common/m2/repository/io/grpc/grpc-netty-shaded/1.56.0", "common/m2/repository/io/grpc/grpc-okhttp/1.0.3", "common/m2/repository/io/grpc/grpc-protobuf-lite/1.0.3", "common/m2/repository/io/grpc/grpc-stub/1.0.3", "common/m2/repository/io/reactivex/rxjava2/rxjava/2.2.9", "common/m2/repository/javax/annotation/javax.annotation-api/1.2", "common/m2/repository/javax/annotation/javax.annotation-api/1.3.2", "common/m2/repository/javax/inject/javax.inject/1", "common/m2/repository/joda-time/joda-time/2.9.1", "common/m2/repository/kotlinx/html/jvm/0.6.8", "common/m2/repository/me/leolin/ShortcutBadger/1.1.13", "common/m2/repository/net/bytebuddy/byte-buddy-agent/1.14.18", "common/m2/repository/net/bytebuddy/byte-buddy/1.14.18", "common/m2/repository/net/java/dev/jna/jna/3.4.0", "common/m2/repository/net/sf/jopt-simple/jopt-simple/4.9", "common/m2/repository/net/sf/trove4j/trove4j/1.1", "common/m2/repository/org/apache/ant/ant/1.8.0", "common/m2/repository/org/apache/commons/commons-lang3/3.4", "common/m2/repository/org/apache/httpcomponents/httpclient/4.0.3", "common/m2/repository/org/apache/httpcomponents/httpcore/4.0.1", "common/m2/repository/org/apache/james/apache-mime4j-core/0.7.2", "common/m2/repository/org/apache/james/apache-mime4j-dom/0.7.2", "common/m2/repository/org/apache/maven/maven-ant-tasks/2.1.3", "common/m2/repository/org/assertj/assertj-core/3.8.0", "common/m2/repository/org/codehaus/mojo/animal-sniffer-annotations/1.14", "common/m2/repository/org/jetbrains/intellij/deps/trove4j/1.0.20181211", "common/m2/repository/org/jetbrains/markdown/0.1.41", "common/m2/repository/org/jsoup/jsoup/1.8.3", "common/m2/repository/org/mockito/mockito-core/4.8.1", "common/m2/repository/org/mockito/mockito-core/5.14.2", "common/m2/repository/org/mockito/mockito-inline/4.8.1", "common/m2/repository/org/reactivestreams/reactive-streams/1.0.2", "common/m2/repository/org/xerial/sqlite-jdbc/3.28.0", "common/m2/repository/ru/yole/jkid"]),
];
const PROVIDER_ADDITIONS_JSON: &str = r#"[{"path":"external/kotlinx.coroutines","name":"platform/external/kotlinx.coroutines","commit":"16161f019a518241332c1cad686a3e9404c0d5cf","purpose":"Exact Android 17 superproject coroutine providers for real AndroidX and StructuredConcurrencyPerf dependencies"},{"path":"external/kotlinx.atomicfu","name":"platform/external/kotlinx.atomicfu","commit":"867bc63054d694773bd0aef56eeb51296f2f6b03","purpose":"Exact Android 17 superproject atomicfu source required by the real coroutine provider"},{"path":"frameworks/libs/systemui","name":"platform/frameworks/libs/systemui","commit":"11e04f60f563aed48e4ec080bd7bde06bae1b2f3","purpose":"Exact Android 17 tracinglib-platform and genuine compilelib providers","sparse_paths":["tracinglib/core/src","compilelib/src-release","compilelib/src-debug"]},{"path":"external/robolectric","name":"platform/external/robolectric","commit":"87aa52b08f0a6bc65f373e0f542a33d8cfb3cfc1","purpose":"Real Robolectric_all-target and its upstream implementation providers required by the parametric runner","sparse_paths":["soong","src/main/resources","annotations/src/main","junit/src/main","nativeruntime/src/main","pluginapi/src/main","resources/src/main","robolectric/src/main","sandbox/src/main","shadowapi/src/main","utils/src/main","utils/reflector/src/main","shadows/framework/src/main","shadows/httpclient/src/main","shadows/multidex/src/main","shadows/versioning/src/main","processor/src/main"]},{"path":"external/TestParameterInjector","name":"platform/external/TestParameterInjector","commit":"39be45d7f8988b7b051e14644bc6c51fe856b8f2","purpose":"Actual TestParameterInjector provider required by real Robolectric libraries","sparse_paths":["junit4/src/main"]},{"path":"external/snakeyaml","name":"platform/external/snakeyaml","commit":"629862ff4a73e7656df0ae02ae0cd24fabf603ae","purpose":"Genuine SnakeYAML implementation and Android patches required by TestParameterInjector","sparse_paths":["src/main","src/patches/android"]},{"path":"test/robolectric-extensions","name":"platform/test/robolectric-extensions","commit":"94254a13a5969eec7a4742320cc3f91e141d5593","purpose":"Real AOSP Robolectric plugin implementation required by Robolectric_all","sparse_paths":["plugins/src/main/java","clearcut-junit-listener/src/main/java"]},{"path":"packages/services/Car","name":"platform/packages/services/Car","commit":"9f04df65daa8b9a65ee05fd4039fe95446874d76","purpose":"Actual android.car and android.car.builtin.impl providers required by the upstream Robolectric host framework","sparse_paths":["aconfig","car-lib/src","car-lib/jni/large-parcelable/src","car-builtin-lib/src","car-builtin-lib/api","libs/car-internal-dep-lib/src","teams"]},{"path":"system/timezone","name":"platform/system/timezone","commit":"cbd571efcf6b551ba83a31147ec7a06182f8ec31","purpose":"Real robolectric_tzdata generator and timezone inputs","sparse_paths":["output_data"]},{"path":"tools/asuite","name":"platform/tools/asuite","commit":"744998cb744c401a5daa77170039ab6337ed7adb","purpose":"Exact Android 17 proto implementation used by the mandatory Robolectric Clearcut JUnit listener","sparse_paths":["atest/proto"]}]"#;
const PATCH: &str = "android/native-role-ingress/typed-ingress02-framework.patch";
const PATCH_BYTES: usize = 17019;
const PATCH_SHA: &str =
    "5a6258c4e60446956cb164ef6796a302e2fb9d48e7f41263572ed51f44015493";
const EXPANDED_PROJECTS: &[&str] = &["frameworks/base", "frameworks/native", "external/skia"];

#[derive(Clone, Copy, Serialize)]
struct Pin {
    bytes: usize,
    sha256: &'static str,
}

#[derive(Clone, Copy, Serialize)]
struct ProjectedInput {
    path: &'static str,
    before: Option<Pin>,
    after: Pin,
}

const INPUTS: &[ProjectedInput] = &[
    ProjectedInput {
        path: "core/java/com/android/internal/os/Zygote.java",
        before: Some(Pin { bytes: 66325, sha256: "1c9d8c4bc1235b514b01c7db81406a770ac7925659d1d7c00a0a7f5dbeac6423" }),
        after: Pin { bytes: 67438, sha256: "9e7ea15e973700f1222ad285638e89833cb6c3463e80d2baf8b03121ed92cbd3" },
    },
    ProjectedInput {
        path: "core/java/com/android/internal/os/ZygoteArguments.java",
        before: Some(Pin { bytes: 22587, sha256: "52e073e4c275f8ebf53b40d654fa3904318f57aedc9f958e64c40da70db5fde5" }),
        after: Pin { bytes: 30540, sha256: "882c44f70b2ef7269f42d9f6d8e4269e28a36d9eecc4bfe2ae1b0cd0fa9162e9" },
    },
    ProjectedInput {
        path: "core/java/com/android/internal/os/ZygoteConnection.java",
        before: Some(Pin { bytes: 26969, sha256: "58f376c5f64387296ef5a669bddc84a5f3d74b94bc7b31b3834233a03aacf746" }),
        after: Pin { bytes: 27831, sha256: "7a23ad09acc3017db09348bf198d74d0fb53cd6c7be66af81918306229f7e516" },
    },
    ProjectedInput {
        path: "core/jni/com_android_internal_os_Zygote.cpp",
        before: Some(Pin { bytes: 130326, sha256: "006e4c3a51fd32eef1d41b3c2553a907e9b7b33b2bf605706921852ba8854a9a" }),
        after: Pin { bytes: 132241, sha256: "72d8cf730e8e3ec4ff4b88106e73e076eab7e761a405a5d854e62e7a5fadc095" },
    },
    ProjectedInput {
        path: "core/jni/droidloom_app_zygote_spec.h",
        before: None,
        after: Pin { bytes: 1647, sha256: "a73c497e4979fcb23b996b8d8d98c63eb48fe1eebe65d7ff9ec87d7d4ab8d1ca" },
    },
];

const BLUEPRINTS: &[(&str, Pin)] = &[
    ("Android.bp", Pin { bytes: 28696, sha256: "9039665725aa013a88f222430e33a1a3e662e23ec87090f253592ee28ec2f545" }),
    ("core/java/Android.bp", Pin { bytes: 32692, sha256: "bde0ed0b9eae4dda4170e84d700c2acf445938f107dd0c094e2cfd1535578fd4" }),
    ("core/jni/Android.bp", Pin { bytes: 24394, sha256: "1a440df74ccbaa2c5b57173bf9f767ba0e4fbcf20c5f39b1ffd485de31b73470" }),
];

fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn real_parents(path: &Path) -> Result<()> {
    if !path.is_absolute()
        || path.components().any(|part| matches!(part, Component::CurDir | Component::ParentDir))
    {
        return fail("typed ingress input/output requires an absolute canonical path");
    }
    for parent in path.ancestors().skip(1) {
        let metadata = fs::symlink_metadata(parent)?;
        if !metadata.is_dir() || metadata.file_type().is_symlink() {
            return fail("typed ingress input/output parent is not a real directory");
        }
    }
    Ok(())
}

fn same_file(left: &Metadata, right: &Metadata) -> bool {
    (left.dev(), left.ino(), left.mode(), left.uid(), left.gid(), left.len(),
        left.mtime(), left.mtime_nsec(), left.ctime(), left.ctime_nsec())
        == (right.dev(), right.ino(), right.mode(), right.uid(), right.gid(), right.len(),
            right.mtime(), right.mtime_nsec(), right.ctime(), right.ctime_nsec())
}

fn bounded_file(path: &Path, bound: usize) -> Result<Vec<u8>> {
    real_parents(path)?;
    let mut file = OpenOptions::new().read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC).open(path)?;
    let before = file.metadata()?;
    if !before.is_file() || before.len() > bound as u64 || bound > 1024 * 1024 {
        return fail(format!("typed ingress input type or bound differs: {}", path.display()));
    }
    let mut bytes = Vec::with_capacity(before.len() as usize);
    (&mut file).take(bound as u64 + 1).read_to_end(&mut bytes)?;
    let after = file.metadata()?;
    let named = fs::symlink_metadata(path)?;
    if bytes.len() != before.len() as usize || bytes.len() > bound
        || !same_file(&before, &after) || !same_file(&before, &named)
    {
        return fail(format!("typed ingress held/named input changed: {}", path.display()));
    }
    Ok(bytes)
}

fn fixed_file(path: &Path, pin: Pin) -> Result<Vec<u8>> {
    let bytes = bounded_file(path, pin.bytes)?;
    if bytes.len() != pin.bytes || digest(&bytes) != pin.sha256 {
        return fail(format!("typed ingress fixed input bytes differ: {}", path.display()));
    }
    Ok(bytes)
}

fn verify_blueprints(source: &Path) -> Result<()> {
    let root = source.join("frameworks/base");
    for (relative, pin) in BLUEPRINTS {
        fixed_file(&root.join(relative), *pin)?;
    }
    Ok(())
}

fn validate_lock_extension(original: &Value, expanded: &Value) -> Result<()> {
    let mut normalized = expanded.clone();
    let original_projects = original.get("projects").and_then(Value::as_array)
        .ok_or("original typed ingress source lock lacks its projects")?;
    let projects = normalized.get_mut("projects").and_then(Value::as_array_mut)
        .ok_or("expanded typed ingress source lock lacks its projects")?;
    if projects.len() != original_projects.len() {
        return fail("typed ingress source lock cannot add or remove projects");
    }
    let mut changed = BTreeSet::new();
    for (before, after) in original_projects.iter().zip(projects.iter_mut()) {
        let path = before.get("path").and_then(Value::as_str)
            .ok_or("original source project path is missing")?;
        if after.get("path").and_then(Value::as_str) != Some(path) {
            return fail("typed ingress source lock changed project paths or ordering");
        }
        if !EXPANDED_PROJECTS.contains(&path) {
            if before != after {
                return fail(format!("typed ingress source lock changed an unrelated project: {path}"));
            }
            continue;
        }
        let old_paths = before.get("sparse_paths").and_then(Value::as_array)
            .ok_or("original bounded project lacks sparse paths")?;
        let new_paths = after.get("sparse_paths").and_then(Value::as_array)
            .ok_or("expanded bounded project lacks sparse paths")?;
        if new_paths.len() <= old_paths.len() || new_paths.len() > 256
            || new_paths.get(..old_paths.len()) != Some(old_paths.as_slice())
        {
            return fail(format!("typed ingress source lock must retain and extend every original sparse path: {path}"));
        }
        let mut seen: BTreeSet<_> = old_paths.iter().filter_map(Value::as_str).collect();
        for value in &new_paths[old_paths.len()..] {
            let name = value.as_str().ok_or("new sparse path is not a string")?;
            let mut components = Path::new(name).components();
            if !matches!(components.next(), Some(Component::Normal(_)))
                || components.next().is_some() || name == ".git" || !seen.insert(name)
            {
                return fail("typed ingress source extension permits only distinct exact root directory names");
            }
        }
        changed.insert(path.to_owned());
        after.as_object_mut().ok_or("source project is not an object")?
            .insert("sparse_paths".to_owned(), before["sparse_paths"].clone());
    }
    if normalized != *original
        || changed != EXPANDED_PROJECTS.iter().map(|name| (*name).to_owned()).collect()
    {
        return fail("typed ingress source lock changed metadata, commits, links or the permitted project set");
    }
    Ok(())
}


fn validate_provider_lock_extension(previous: &Value, expanded: &Value) -> Result<()> {
    let mut expected = previous.clone();
    let projects = expected.get_mut("projects").and_then(Value::as_array_mut)
        .ok_or("previous typed lock lacks projects")?;
    for (path, additions) in PROVIDER_EXTENSIONS {
        let indices: Vec<_> = projects.iter().enumerate()
            .filter(|(_, project)| project.get("path").and_then(Value::as_str) == Some(*path))
            .map(|(index, _)| index).collect();
        if indices.len() != 1 || additions.is_empty() {
            return fail("provider closure requires exactly one existing locked project");
        }
        let paths = projects[indices[0]].get_mut("sparse_paths").and_then(Value::as_array_mut)
            .ok_or("provider closure project has no existing sparse selection")?;
        for addition in *additions {
            let value = Value::String((*addition).to_owned());
            if paths.contains(&value) {
                return fail("provider closure repeats an existing sparse path");
            }
            paths.push(value);
        }
        if paths.len() > 256 {
            return fail("provider closure exceeds the existing bounded sparse selection");
        }
    }
    let additions: Vec<Value> = serde_json::from_str(PROVIDER_ADDITIONS_JSON)?;
    for addition in additions {
        let path = addition.get("path").and_then(Value::as_str)
            .ok_or("provider addition lacks an exact path")?;
        if projects.iter().any(|project| project.get("path").and_then(Value::as_str) == Some(path)) {
            return fail("provider closure replaces an existing project");
        }
        projects.push(addition);
    }
    if &expected != expanded {
        return fail("provider closure changed the exact previous lock or its fixed upstream additions");
    }
    Ok(())
}

fn validate_native_provider_extension(previous: &Value, expanded: &Value) -> Result<()> {
    let mut expected = previous.clone();
    let projects = expected.get_mut("projects").and_then(Value::as_array_mut)
        .ok_or("previous provider lock lacks projects")?;
    let indices: Vec<_> = projects.iter().enumerate()
        .filter(|(_, project)| project.get("path").and_then(Value::as_str) == Some("packages/services/Car"))
        .map(|(index, _)| index).collect();
    if indices.len() != 1 {
        return fail("native provider extension requires the one original Car project");
    }
    let paths = projects[indices[0]].get_mut("sparse_paths").and_then(Value::as_array_mut)
        .ok_or("original Car provider lacks sparse paths")?;
    for path in CAR_NATIVE_EXTENSIONS {
        let value = Value::String((*path).to_owned());
        if paths.contains(&value) {
            return fail("native provider extension repeats a Car path");
        }
        paths.push(value);
    }
    if paths.len() > 256 {
        return fail("native provider extension exceeds bounded Car paths");
    }
    let addition: Value = serde_json::from_str(NEURALNETWORKS_ADDITION_JSON)?;
    if projects.iter().any(|project| project.get("path") == addition.get("path")) {
        return fail("native provider extension replaces NeuralNetworks");
    }
    projects.push(addition);
    if &expected != expanded {
        return fail("native provider extension changed fixed commits, metadata, order or source paths");
    }
    Ok(())
}

fn materialized_previous_lock(value: &Value) -> Result<Option<(&'static str, Pin)>> {
    match value.get("source_lock_sha256").and_then(Value::as_str) {
        Some(SOURCE_LOCK_SHA) => Ok(None),
        Some(PREVIOUS_PROVIDER_LOCK_SHA) => Ok(Some(("m2-role-ingress-provider-source-lock.json", Pin {
            bytes: PREVIOUS_PROVIDER_LOCK_BYTES, sha256: PREVIOUS_PROVIDER_LOCK_SHA,
        }))),
        Some(PREVIOUS_SOURCE_LOCK_SHA) => Ok(Some(("m2-role-ingress-source-lock.json", Pin {
            bytes: PREVIOUS_SOURCE_LOCK_BYTES, sha256: PREVIOUS_SOURCE_LOCK_SHA,
        }))),
        _ => fail("typed provider source workspace belongs to no exact permitted typed lock"),
    }
}

pub fn source_lock_path(repo: &Path) -> Result<PathBuf> {
    let original = fixed_file(&repo.join(ORIGINAL_LOCK), Pin {
        bytes: ORIGINAL_LOCK_BYTES, sha256: ORIGINAL_LOCK_SHA,
    })?;
    let path = repo.join(SOURCE_LOCK);
    let expanded = fixed_file(&path, Pin {
        bytes: SOURCE_LOCK_BYTES, sha256: SOURCE_LOCK_SHA,
    })?;
    let previous = fixed_file(&repo.join(PREVIOUS_SOURCE_LOCK), Pin {
        bytes: PREVIOUS_SOURCE_LOCK_BYTES, sha256: PREVIOUS_SOURCE_LOCK_SHA,
    })?;
    let previous_value: Value = serde_json::from_slice(&previous)?;
    validate_lock_extension(&serde_json::from_slice(&original)?, &previous_value)?;
    let previous_provider = fixed_file(&repo.join(PREVIOUS_PROVIDER_LOCK), Pin {
        bytes: PREVIOUS_PROVIDER_LOCK_BYTES, sha256: PREVIOUS_PROVIDER_LOCK_SHA,
    })?;
    let previous_provider_value: Value = serde_json::from_slice(&previous_provider)?;
    validate_provider_lock_extension(&previous_value, &previous_provider_value)?;
    validate_native_provider_extension(&previous_provider_value, &serde_json::from_slice(&expanded)?)?;
    // The normal source library validates the full lock schema, exact revisions,
    // URL policy, path bounds and every materialized Git project separately.
    droidloom_source::load_lock(&path)?;
    Ok(path)
}

pub fn verify_source_workspace(
    lock_path: &Path,
    lock: &droidloom_source::SparseSourceLock,
    source: &Path,
) -> Result<()> {
    real_parents(source)?;
    match fs::symlink_metadata(source) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error.into()),
        Ok(metadata) if metadata.is_dir() && !metadata.file_type().is_symlink() => {
            // Select the exact current, provider1 or earlier independent typed lock before
            // running its complete verifier. A dirty/mismatched previous tree never
            // falls back to the new lock; the original shared sparse lock stays blocked.
            let manifest: Value = serde_json::from_slice(&bounded_file(
                &source.join(".droidloom-source-manifest.json"), 1024 * 1024)?)?;
            if let Some((name, pin)) = materialized_previous_lock(&manifest)? {
                let previous_path = lock_path.with_file_name(name);
                fixed_file(&previous_path, pin)?;
                let previous = droidloom_source::load_lock(&previous_path)?;
                droidloom_source::verify_materialized(&previous_path, &previous, source)?;
            } else {
                droidloom_source::verify_materialized(lock_path, lock, source)?;
            }
            Ok(())
        }
        Ok(_) => fail("typed ingress source workspace is not a real directory"),
    }
}

pub fn validated_output(work: &Path, out: &Path) -> Result<PathBuf> {
    let source = work.join("aosp-source");
    real_parents(out)?;
    if out.starts_with(&source) || source.starts_with(out) {
        return fail("typed ingress output overlaps its source workspace");
    }
    match fs::symlink_metadata(out) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(out.to_owned()),
        Err(error) => Err(error.into()),
        Ok(_) => fail("typed ingress output already exists; a fresh output is required"),
    }
}

fn create_record(path: &Path, value: Value) -> Result<()> {
    let mut file = OpenOptions::new().write(true).create_new(true).mode(0o600).open(path)?;
    file.write_all(&serde_json::to_vec_pretty(&value)?)?;
    file.write_all(b"\n")?;
    file.sync_all()?;
    Ok(())
}

pub fn begin_attempt(repo: &Path, work: &Path, out: &Path) -> Result<()> {
    validated_output(work, out)?;
    let lock = source_lock_path(repo)?;
    fs::create_dir(out)?;
    create_record(&out.join("droidloom-role-ingress-attempt.json"), serde_json::json!({
        "schema": 1, "state": "CLAIMED_BEFORE_SOURCE_MATERIALIZATION_OR_PROJECTION",
        "targets": TARGETS, "dependency_mode": "Strict",
        "source_lock": lock, "source_lock_sha256": hash(&lock)?,
        "original_source_lock_sha256": ORIGINAL_LOCK_SHA,
        "source_projection_journal": work.join("source-projection.json"),
        "runtime_authorization_enabled": false, "installation_performed": false,
        "transitive_build_closure_qualified": false,
        "complete_framework_Java_and_Android_TU_verified": false,
    }))
}

pub fn verified_patch(repo: &Path, source: &Path) -> Result<PathBuf> {
    let patch = repo.join(PATCH);
    fixed_file(&patch, Pin { bytes: PATCH_BYTES, sha256: PATCH_SHA })?;
    verify_blueprints(source)?;
    let root = source.join("frameworks/base");
    // Check all four original files and the new header's absence before the
    // normal Projection::patch performs its first write and records its journal.
    for input in INPUTS {
        let path = root.join(input.path);
        if let Some(pin) = input.before {
            fixed_file(&path, pin)?;
        } else {
            real_parents(&path)?;
            match fs::symlink_metadata(&path) {
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {},
                Err(error) => return Err(error.into()),
                Ok(_) => return fail("typed ingress new header path already exists"),
            }
        }
    }
    Ok(patch)
}

pub fn verify_projected(source: &Path) -> Result<()> {
    let root = source.join("frameworks/base");
    for input in INPUTS {
        fixed_file(&root.join(input.path), input.after)?;
    }
    verify_blueprints(source)
}

pub fn write_inputs(
    repo: &Path,
    source: &Path,
    out: &Path,
    selected_targets: &[PathBuf],
    projection_inventory: Value,
) -> Result<()> {
    let selected: Vec<_> = selected_targets.iter().map(|path| path.to_str()).collect();
    if selected != TARGETS.iter().map(|name| Some(*name)).collect::<Vec<_>>() {
        return fail("typed ingress resolved target list differs from the two complete modules");
    }
    verify_projected(source)?;
    let lock = source_lock_path(repo)?;
    create_record(&out.join("droidloom-role-ingress-inputs.json"), serde_json::json!({
        "schema": 1, "targets": selected_targets, "dependency_mode": "Strict",
        "source_lock": lock, "source_lock_sha256": hash(&lock)?,
        "original_source_lock_sha256": ORIGINAL_LOCK_SHA,
        "previous_typed_source_lock_sha256": PREVIOUS_SOURCE_LOCK_SHA,
        "previous_provider_source_lock_sha256": PREVIOUS_PROVIDER_LOCK_SHA,
        "provider_source_lock_extension_exact": true,
        "native_provider_extension_exact": true,
        "typed_ingress_sources": INPUTS, "unchanged_framework_module_definitions": BLUEPRINTS,
        "source_projection": projection_inventory,
        "required_compiled_Java_sources": ["frameworks/base/core/java/com/android/internal/os/Zygote.java",
            "frameworks/base/core/java/com/android/internal/os/ZygoteArguments.java",
            "frameworks/base/core/java/com/android/internal/os/ZygoteConnection.java"],
        "required_Android_TU": "frameworks/base/core/jni/com_android_internal_os_Zygote.cpp",
        "required_Android_header": "frameworks/base/core/jni/droidloom_app_zygote_spec.h",
        "host_only_libandroid_runtime_is_insufficient": true,
        "runtime_authorization_enabled": false,
        "complete_framework_Java_and_Android_TU_verified": false,
        "transitive_build_closure_qualified": false,
    }))
}

pub fn write_command_completion(out: &Path) -> Result<()> {
    create_record(&out.join("droidloom-role-ingress-command.json"), serde_json::json!({
        "schema": 1, "state": "NORMAL_BUILD_COMMAND_SUCCEEDED",
        "source_projection_restored": true, "installation_performed": false,
        "runtime_authorization_enabled": false,
        "complete_framework_Java_and_Android_TU_verified": false,
        "actual_Java_JNI_pair_and_platform_lifecycle_qualified": false,
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn repository() -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent().unwrap().parent().unwrap().to_owned()
    }

    #[test]
    fn observed_lock_passes_normal_schema_and_exact_extension_gate() {
        let repo = repository();
        let path = source_lock_path(&repo).unwrap();
        assert_eq!(path, repo.join(SOURCE_LOCK));
        let bytes = fixed_file(&path, Pin {
            bytes: SOURCE_LOCK_BYTES, sha256: SOURCE_LOCK_SHA,
        }).unwrap();
        assert_eq!(bytes.len(), SOURCE_LOCK_BYTES);
        assert_eq!(digest(&bytes), SOURCE_LOCK_SHA);
    }

    #[test]
    fn structurally_valid_unobserved_root_is_rejected_before_source_actions() {
        let repo = repository();
        let original = fixed_file(&repo.join(ORIGINAL_LOCK), Pin {
            bytes: ORIGINAL_LOCK_BYTES, sha256: ORIGINAL_LOCK_SHA,
        }).unwrap();
        let expanded = fixed_file(&repo.join(PREVIOUS_SOURCE_LOCK), Pin {
            bytes: PREVIOUS_SOURCE_LOCK_BYTES, sha256: PREVIOUS_SOURCE_LOCK_SHA,
        }).unwrap();
        let current = fixed_file(&repo.join(SOURCE_LOCK), Pin {
            bytes: SOURCE_LOCK_BYTES, sha256: SOURCE_LOCK_SHA,
        }).unwrap();
        let original_value: Value = serde_json::from_slice(&original).unwrap();
        let mut changed: Value = serde_json::from_slice(&expanded).unwrap();
        let project = changed["projects"].as_array_mut().unwrap().iter_mut()
            .find(|project| project["path"] == "frameworks/base").unwrap();
        let paths = project["sparse_paths"].as_array_mut().unwrap();
        paths.push(Value::String("unobserved-role-ingress-root".to_owned()));
        // This is the old shape gate's accepted case. The public entry must
        // additionally require the actual derived bytes before any source work.
        validate_lock_extension(&original_value, &changed).unwrap();
        let scratch = tempfile::tempdir().unwrap();
        let manifest = scratch.path().join("android/manifest");
        fs::create_dir_all(&manifest).unwrap();
        fs::write(scratch.path().join(ORIGINAL_LOCK), &original).unwrap();
        fs::write(scratch.path().join(SOURCE_LOCK), current).unwrap();
        fs::write(scratch.path().join(PREVIOUS_SOURCE_LOCK), serde_json::to_vec_pretty(&changed).unwrap())
            .unwrap();
        let error = source_lock_path(scratch.path()).unwrap_err().to_string();
        assert!(error.contains(PREVIOUS_SOURCE_LOCK));
        assert!(error.contains("typed ingress fixed input bytes differ")
            || error.contains("typed ingress input type or bound differs"));
        assert!(!scratch.path().join("aosp-source").exists());
        assert!(!scratch.path().join("source-projection.json").exists());
        assert_eq!(fs::read(scratch.path().join(ORIGINAL_LOCK)).unwrap(), original);
    }

    #[test]
    fn provider_extension_rejects_unlisted_path_commit_metadata_or_project_change() {
        let repo = repository();
        let previous: Value = serde_json::from_slice(&fs::read(repo.join(PREVIOUS_SOURCE_LOCK)).unwrap()).unwrap();
        let expanded: Value = serde_json::from_slice(&fs::read(repo.join(PREVIOUS_PROVIDER_LOCK)).unwrap()).unwrap();
        validate_provider_lock_extension(&previous, &expanded).unwrap();
        let mut changed = expanded.clone();
        changed["projects"][0]["commit"] = Value::String("0000000000000000000000000000000000000000".to_owned());
        assert!(validate_provider_lock_extension(&previous, &changed).is_err());
        let mut changed = expanded.clone();
        changed["status"] = Value::String("unqualified-metadata-change".to_owned());
        assert!(validate_provider_lock_extension(&previous, &changed).is_err());
        let mut changed = expanded.clone();
        changed["projects"].as_array_mut().unwrap().pop();
        assert!(validate_provider_lock_extension(&previous, &changed).is_err());
        let mut changed = expanded.clone();
        let project = changed["projects"].as_array_mut().unwrap().iter_mut()
            .find(|project| project["path"] == PROVIDER_EXTENSIONS[0].0).unwrap();
        project["sparse_paths"].as_array_mut().unwrap()
            .push(Value::String("unobserved-provider-path".to_owned()));
        assert!(validate_provider_lock_extension(&previous, &changed).is_err());
    }

    #[test]
    fn native_provider_extension_rejects_missing_or_unpinned_providers() {
        let repo = repository();
        let previous: Value = serde_json::from_slice(&fs::read(repo.join(PREVIOUS_PROVIDER_LOCK)).unwrap()).unwrap();
        let expanded: Value = serde_json::from_slice(&fs::read(repo.join(SOURCE_LOCK)).unwrap()).unwrap();
        validate_native_provider_extension(&previous, &expanded).unwrap();
        let mut changed = expanded.clone();
        changed["projects"].as_array_mut().unwrap().last_mut().unwrap()["commit"] =
            Value::String("0000000000000000000000000000000000000000".to_owned());
        assert!(validate_native_provider_extension(&previous, &changed).is_err());
        let mut changed = expanded.clone();
        let car = changed["projects"].as_array_mut().unwrap().iter_mut()
            .find(|project| project["path"] == "packages/services/Car").unwrap();
        car["sparse_paths"].as_array_mut().unwrap().pop();
        assert!(validate_native_provider_extension(&previous, &changed).is_err());
        let mut changed = expanded.clone();
        changed["projects"].as_array_mut().unwrap().pop();
        assert!(validate_native_provider_extension(&previous, &changed).is_err());
        let mut changed = expanded.clone();
        changed["projects"][0]["commit"] =
            Value::String("0000000000000000000000000000000000000000".to_owned());
        assert!(validate_native_provider_extension(&previous, &changed).is_err());
    }

    #[test]
    fn published_workspace_selects_only_exact_current_or_previous_typed_lock() {
        assert!(materialized_previous_lock(&serde_json::json!({"source_lock_sha256": SOURCE_LOCK_SHA})).unwrap().is_none());
        for (sha, name) in [(PREVIOUS_SOURCE_LOCK_SHA, "m2-role-ingress-source-lock.json"),
                            (PREVIOUS_PROVIDER_LOCK_SHA, "m2-role-ingress-provider-source-lock.json")] {
            assert_eq!(materialized_previous_lock(&serde_json::json!({"source_lock_sha256": sha})).unwrap().unwrap().0, name);
        }
        for value in [serde_json::json!({"source_lock_sha256": ORIGINAL_LOCK_SHA}),
                      serde_json::json!({"source_lock_sha256": "unknown"}),
                      serde_json::json!({}), serde_json::json!(null)] {
            assert!(materialized_previous_lock(&value).is_err());
        }
    }


    #[test]
    fn previous_typed_manifest_does_not_bypass_fresh_project_verification() {
        let repo = repository();
        let current_path = source_lock_path(&repo).unwrap();
        let current = droidloom_source::load_lock(&current_path).unwrap();
        for (previous_name, previous_sha) in [(PREVIOUS_SOURCE_LOCK, PREVIOUS_SOURCE_LOCK_SHA),
                                             (PREVIOUS_PROVIDER_LOCK, PREVIOUS_PROVIDER_LOCK_SHA)] {
            let previous = droidloom_source::load_lock(&repo.join(previous_name)).unwrap();
            let scratch = tempfile::tempdir().unwrap();
            let source = scratch.path().join("aosp-source");
            fs::create_dir(&source).unwrap();
            let manifest = serde_json::to_vec_pretty(&serde_json::json!({
                "schema_version": 1,
                "source_lock_sha256": previous_sha,
                "plan": droidloom_source::build_plan(&previous).unwrap(),
            })).unwrap();
            let manifest_path = source.join(".droidloom-source-manifest.json");
            fs::write(&manifest_path, &manifest).unwrap();
            // An exact old manifest still reaches and fails the real Git
            // verifier when its projects are missing. No fallback or rewrite.
            let error = verify_source_workspace(&current_path, &current, &source).unwrap_err();
            match error.downcast_ref::<droidloom_source::SourceError>() {
                Some(droidloom_source::SourceError::Command { program, .. }) => assert_eq!(program, "git"),
                other => panic!("expected fresh missing-checkout verification, got {other:?}"),
            }
            assert_eq!(fs::read(&manifest_path).unwrap(), manifest);
            assert_eq!(fs::read_dir(&source).unwrap().count(), 1);
            assert!(!scratch.path().join("source-projection.json").exists());
        }
    }

}
