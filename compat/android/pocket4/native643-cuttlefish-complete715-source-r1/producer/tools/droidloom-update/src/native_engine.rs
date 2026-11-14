//! Provenance for the explicit engine leaf. This never stages a runtime/image.
use crate::{native_bridge, util::*};
use serde_json::{Value, json};
use std::{
    collections::BTreeSet,
    fs,
    path::{Path, PathBuf},
    process::Command,
};

const ENGINE: &str = "system/lib64/libberberis_arm64.so";
const TEST_DIR: &str = "host/linux-x86/nativetest64/berberis_arm64_host_tests";
const TEST_DATA: &[&str] = &[
    "decoder/arm64_test/arm64_decoder_encodings.txt",
    "decoder/arm64_test/arm64_decoder_undefined_baseline.txt",
    "heavy_optimizer/arm64/arm64_tier_coverage.txt",
];
const TEST_LIBRARIES: &[&str] = &["libbase.so", "liblog.so", "libc++.so"];

pub(crate) fn begin_attempt(out: &Path, product: &str) -> Result<()> {
    let directory = out.join("target/product").join(product);
    for name in [
        "droidloom-native-engine-source.json",
        "droidloom-native-engine-inputs.json",
    ] {
        let path = directory.join(name);
        match fs::remove_file(&path) {
            Ok(()) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => return Err(error.into()),
        }
    }
    Ok(())
}

pub(crate) fn write_inputs(out: &Path, product: &str, inputs: &Value) -> Result<()> {
    durable_write(
        &out.join("target/product")
            .join(product)
            .join("droidloom-native-engine-inputs.json"),
        serde_json::to_vec_pretty(inputs)?,
    )
}

fn elf_header(path: &Path) -> Result<Value> {
    use std::io::Read;
    let mut header = [0u8; 20];
    fs::File::open(path)?.read_exact(&mut header)?;
    if &header[..6] != b"\x7fELF\x02\x01" || u16::from_le_bytes([header[18], header[19]]) != 62 {
        return fail(format!(
            "engine artifact is not ELF64 little-endian x86_64: {}",
            path.display()
        ));
    }
    Ok(json!({"class": "ELF64", "endianness": "little", "machine": "EM_X86_64"}))
}

fn release_compiler(source: &Path) -> Result<String> {
    let text = fs::read_to_string(
        source.join("build/release/flag_values/cp2a/RELEASE_BUILD_CLANG_VERSION.textproto"),
    )?;
    let values: Vec<_> = text
        .lines()
        .filter_map(|line| {
            line.trim()
                .strip_prefix("string_value:")?
                .trim()
                .strip_prefix('"')?
                .strip_suffix('"')
        })
        .collect();
    if values.len() != 1
        || !values[0].starts_with("clang-r")
        || !values[0]
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || c == b'-')
    {
        return fail("cp2a release must select exactly one pinned Clang revision");
    }
    Ok(values[0].to_owned())
}

pub(crate) fn engine_build_inputs(
    repo: &Path,
    source: &Path,
    vendor: &Path,
    work: &Path,
    out: &Path,
    source_snapshot: &Value,
    targets: &[&str],
    selected_targets: &[PathBuf],
    effective_projection: Value,
) -> Result<Value> {
    let bridge_lock_path = repo.join("android/manifest/native-bridge-lock.json");
    let aosp_lock_path = repo.join("android/manifest/m2-sparse-source-lock.json");
    let bridge_lock: Value = serde_json::from_slice(&fs::read(&bridge_lock_path)?)?;
    let bridge_path = bridge_lock["path"]
        .as_str()
        .ok_or("bridge lock lacks source path")?;
    let aosp_lock: Value = serde_json::from_slice(&fs::read(&aosp_lock_path)?)?;
    let compiler_project = aosp_lock["projects"]
        .as_array()
        .ok_or("source lock lacks projects")?
        .iter()
        .find(|p| p["path"] == "prebuilts/clang/host/linux-x86")
        .ok_or("source lock lacks original Clang project")?;
    let baseline = work.join("base-system/system/lib64/libandroid.so");
    let reference = vendor.join("android/native-bridge/link/libandroid.so");
    let baseline_hash = hash(&baseline)?;
    if baseline_hash != hash(&reference)? {
        return fail("engine libandroid link reference differs from the frozen baseline");
    }
    let compiler_revision = release_compiler(source)?;
    let compiler_root = source
        .join("prebuilts/clang/host/linux-x86")
        .join(&compiler_revision);
    let reference_identity = artifact(source, &compiler_revision, &reference)?;
    if reference_identity["metadata"]["soname"] != "libandroid.so" {
        return fail("frozen engine libandroid reference has an unexpected SONAME");
    }
    let mut builder_files = std::collections::BTreeMap::new();
    for relative in [
        "Cargo.lock",
        "tools/droidloom-update/src/main.rs",
        "tools/droidloom-update/src/android.rs",
        "tools/droidloom-update/src/native_bridge.rs",
        "tools/droidloom-update/src/native_engine.rs",
    ] {
        builder_files.insert(relative, hash(&repo.join(relative))?);
    }
    Ok(json!({
        "schema_version": 1, "scope": "native-engine-only", "status": "inputs_captured",
        "output_directory": out,
        "local_source_import_policy": "checksum-no-times-v1; migrate old timestamp-preserving caches with a fresh output directory",
        "logical_targets": targets, "ninja_targets": selected_targets,
        "source": bridge_lock, "source_snapshot": source_snapshot,
        "effective_teto_files": native_bridge::source_inventory(&source.join(bridge_path))?,
        "effective_projection": effective_projection,
        "source_lock_sha256": hash(&aosp_lock_path)?,
        "native_bridge_lock_sha256": hash(&bridge_lock_path)?,
        "superproject": aosp_lock["superproject"], "compiler_project": compiler_project,
        "compiler_revision": compiler_revision,
        "compiler_entry_sha256": hash(&compiler_root.join("bin/clang"))?,
        "builder_files": builder_files,
        "link_references": [{
            "module": "droidloom_native_bridge_host_libandroid",
            "sha256": baseline_hash, "identity": reference_identity,
            "origin": "frozen base-system/system/lib64/libandroid.so",
            "prepared_reference_matches_frozen_baseline": true,
            "provider_blueprint_sha256": hash(&vendor.join("android/native-bridge/link/Android.bp"))?,
            "existing_provider_elf_dependency_check_disabled": true,
            "installed_runtime_compatibility_verified": false, "replacement_output": false
        }],
        "tests_requested": targets.contains(&"berberis_arm64_host_tests"),
        "full_runtime_rebuilt": false, "full_product_qualified": false,
        "runtime_compatibility_verified": false, "installation_performed": false
    }))
}

// Keep only ELF identity/import/export metadata, never readelf's entire output.
fn parse_elf_metadata(text: &str) -> Value {
    let mut needed = BTreeSet::new();
    let mut exports = BTreeSet::new();
    let mut undefined = BTreeSet::new();
    let mut soname = None;
    let mut build_id = None;
    for line in text.lines() {
        if let Some(id) = line.trim().strip_prefix("Build ID:") {
            let id = id.trim();
            if !id.is_empty() && id.bytes().all(|c| c.is_ascii_hexdigit()) {
                build_id = Some(id.to_owned());
            }
        }
        let bracket = line
            .split_once('[')
            .and_then(|(_, tail)| tail.split_once(']').map(|x| x.0));
        if line.contains("(NEEDED)") {
            if let Some(name) = bracket {
                needed.insert(name.to_owned());
            }
        } else if line.contains("(SONAME)") {
            soname = bracket.map(str::to_owned);
        }
        let fields: Vec<_> = line.split_whitespace().collect();
        if fields.len() >= 8
            && fields[0].ends_with(':')
            && fields[0].trim_end_matches(':').parse::<usize>().is_ok()
            && matches!(fields[4], "GLOBAL" | "WEAK")
        {
            if fields[6] == "UND" {
                undefined.insert(fields[7].to_owned());
            } else {
                exports.insert(fields[7].to_owned());
            }
        }
    }
    json!({"build_id": build_id, "soname": soname, "needed": needed,
        "exported_dynamic_symbols": exports, "undefined_dynamic_symbols": undefined})
}

fn artifact(source: &Path, compiler: &str, path: &Path) -> Result<Value> {
    let elf = elf_header(path)?;
    let readelf = source
        .join("prebuilts/clang/host/linux-x86")
        .join(compiler)
        .join("bin/llvm-readelf");
    let metadata = output(
        Command::new(readelf)
            .args(["--notes", "--dynamic", "--dyn-syms", "--wide"])
            .arg(path),
    )?;
    Ok(json!({"sha256": hash(path)?, "elf": elf, "metadata": parse_elf_metadata(&metadata)}))
}

pub(crate) fn write_engine_build_receipt(
    source: &Path,
    out: &Path,
    product: &str,
    mut inputs: Value,
) -> Result<()> {
    if inputs["output_directory"] != json!(out) {
        return fail("engine input receipt output directory differs from the selected build output");
    }
    let compiler = inputs["compiler_revision"]
        .as_str()
        .ok_or("engine inputs lack compiler revision")?
        .to_owned();
    let product_dir = out.join("target/product").join(product);
    let engine = artifact(source, &compiler, &product_dir.join(ENGINE))?;
    if engine["metadata"]["soname"] != "libberberis_arm64.so"
        || !engine["metadata"]["exported_dynamic_symbols"]
            .as_array()
            .is_some_and(|symbols| {
                symbols.iter().any(|s| {
                    s.as_str()
                        .is_some_and(|name| name.split('@').next() == Some("NativeBridgeItf"))
                })
            })
    {
        return fail("built engine lacks its original SONAME or NativeBridgeItf export");
    }
    inputs["engine"] = engine;
    inputs["engine"]["path"] = json!(product_dir.join(ENGINE));
    if inputs["tests_requested"] == true {
        let directory = out.join(TEST_DIR);
        let mut data = std::collections::BTreeMap::new();
        for relative in TEST_DATA {
            data.insert(*relative, hash(&directory.join(relative))?);
        }
        let mut libraries = std::collections::BTreeMap::new();
        for name in TEST_LIBRARIES {
            libraries.insert(
                *name,
                artifact(
                    source,
                    &compiler,
                    &out.join("host/linux-x86/lib64").join(name),
                )?,
            );
        }
        inputs["host_tests"] = json!({
            "directory": directory,
            "binary_path": directory.join("berberis_arm64_host_tests"),
            "shared_library_directory": out.join("host/linux-x86/lib64"),
            "variant": "linux_glibc_x86_64", "guest_architecture": "arm64",
            "binary": artifact(source, &compiler, &directory.join("berberis_arm64_host_tests"))?,
            "data": data, "shared_libraries": libraries, "built": true, "executed": false,
            "qualification": "Run the real host suite separately with these staged data and matching host shared libraries"
        });
    }
    inputs["status"] = "selected_artifacts_built".into();
    durable_write(
        &product_dir.join("droidloom-native-engine-source.json"),
        serde_json::to_vec_pretty(&inputs)?,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn native_engine_attempt_cannot_reuse_an_old_success_or_whole_bridge_manifest() {
        let root = tempfile::tempdir().unwrap();
        let directory = root.path().join("target/product/test");
        for name in [
            "droidloom-native-engine-source.json",
            "droidloom-native-engine-inputs.json",
            "droidloom-native-bridge-source.json",
        ] {
            write(&directory.join(name), "old receipt").unwrap();
        }
        begin_attempt(root.path(), "test").unwrap();
        assert!(
            !directory
                .join("droidloom-native-engine-source.json")
                .exists()
        );
        assert!(
            !directory
                .join("droidloom-native-engine-inputs.json")
                .exists()
        );
        assert_eq!(
            fs::read_to_string(directory.join("droidloom-native-bridge-source.json")).unwrap(),
            "old receipt"
        );
        let inputs = json!({"scope": "native-engine-only", "status": "inputs_captured"});
        write_inputs(root.path(), "test", &inputs).unwrap();
        assert_eq!(
            serde_json::from_slice::<Value>(
                &fs::read(directory.join("droidloom-native-engine-inputs.json")).unwrap()
            )
            .unwrap(),
            inputs
        );
        assert!(
            !directory
                .join("droidloom-native-engine-source.json")
                .exists()
        );
    }

    #[test]
    fn native_engine_receipt_refuses_a_different_output_before_reading_artifacts() {
        let inputs = json!({"output_directory": "/old-out"});
        let error = write_engine_build_receipt(
            Path::new("/no-source-access"), Path::new("/new-out"), "test", inputs)
            .unwrap_err().to_string();
        assert_eq!(error, "engine input receipt output directory differs from the selected build output");
    }

    #[test]
    fn native_engine_elf_metadata_preserves_real_imports_exports_and_versions() {
        let value = parse_elf_metadata(
            "\nBuild ID: abc0123\n 0x1 (NEEDED) Shared library: [liblog.so]\n 0xe (SONAME) Library soname: [libberberis_arm64.so]\n 1: 0 0 OBJECT GLOBAL DEFAULT 12 NativeBridgeItf\n 2: 0 0 FUNC GLOBAL DEFAULT UND dlopen@LIBC\n 3: 0 0 FUNC LOCAL DEFAULT 12 private_impl\n",
        );
        assert_eq!(value["build_id"], "abc0123");
        assert_eq!(value["soname"], "libberberis_arm64.so");
        assert_eq!(value["needed"], json!(["liblog.so"]));
        assert_eq!(
            value["exported_dynamic_symbols"],
            json!(["NativeBridgeItf"])
        );
        assert_eq!(value["undefined_dynamic_symbols"], json!(["dlopen@LIBC"]));
    }

    #[test]
    fn native_engine_release_compiler_rejects_ambiguous_or_escaping_revision() {
        let root = tempfile::tempdir().unwrap();
        let path = root
            .path()
            .join("build/release/flag_values/cp2a/RELEASE_BUILD_CLANG_VERSION.textproto");
        write(&path, "value {\n string_value: \"clang-r584948b\"\n}\n").unwrap();
        assert_eq!(release_compiler(root.path()).unwrap(), "clang-r584948b");
        write(&path, "string_value: \"clang-r/../../other\"\n").unwrap();
        assert!(release_compiler(root.path()).is_err());
        write(
            &path,
            "string_value: \"clang-r1\"\nstring_value: \"clang-r2\"\n",
        )
        .unwrap();
        assert!(release_compiler(root.path()).is_err());
    }
}
