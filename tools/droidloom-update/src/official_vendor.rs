//! Independent vendor production from exact CP3A binary interfaces.
//!
//! Two ordinary strict user builds preserve the full651 union, its exact CMake extension and neverallow
//! contracts. The first builds a normal Soong NativeBridge distribution; the
//! second installs those checked outputs into vendor through ordinary prebuilt
//! modules. Neither phase modifies, relabels or replaces the official system.
use super::*;
use droidloom_image::official_vendor_inputs::{
    PROFILE_SHA256, SYSTEM_SHA256, VerifiedVendorInputs,
};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::os::unix::fs::MetadataExt;
use std::process::Stdio;
use std::time::{Duration, Instant};

pub(super) const NATIVE_TARGETS: &[&str] = &["droidloom_cp3a_native_bridge_package"];
pub(super) const VENDOR_TARGETS: &[&str] = &["vendorimage", "secilc", "checkvintf"];
const HOST_DIRECTORY: &str = "lib64/droidloom/nativebridge";
const GUEST_DIRECTORY: &str = "etc/droidloom/nativebridge/guest";
const INPUT_NAME: &str = "droidloom-official-gsi-vendor-inputs.json";
const RESULT_NAME: &str = "droidloom-official-gsi-vendor-normal-result.json";
const VENDOR_FILE_CONTEXTS: &str = include_str!("official_vendor_file_contexts");
use droidloom_contracts::system_ext::HOST_MODULES;
const GUEST_MODULES: &[&str] = &[
    "libnative_bridge_vdso",
    "native_bridge_guest_app_process",
    "native_bridge_guest_linker",
    "libandroidicu",
    "libcompiler_rt",
    "libcrypto",
    "libcutils",
    "libdl",
    "libdl_android",
    "libicu",
    "libicui18n",
    "libicuuc",
    "liblog",
    "libsqlite",
    "libssl",
    "libstdc++",
    "libsync",
    "libutils",
    "libz",
    "libbase",
    "libc++",
    "libvndksupport",
    "libgui_digitalis_guest_stub",
    "libnative_bridge_guest_libaaudio",
    "libnative_bridge_guest_libamidi",
    "libnative_bridge_guest_libandroid",
    "libnative_bridge_guest_libandroid_runtime",
    "libnative_bridge_guest_libbinder_ndk",
    "//frameworks/libs/native_bridge_support/android_api/libc:libnative_bridge_guest_libc",
    "libnative_bridge_guest_libcamera2ndk",
    "libnative_bridge_guest_libEGL",
    "libnative_bridge_guest_libGLESv1_CM",
    "libnative_bridge_guest_libGLESv2",
    "libnative_bridge_guest_libGLESv3",
    "libnative_bridge_guest_libjnigraphics",
    "libnative_bridge_guest_libm",
    "libnative_bridge_guest_libmediandk",
    "libnative_bridge_guest_libnativehelper",
    "libnative_bridge_guest_libnativewindow",
    "libnative_bridge_guest_libneuralnetworks",
    "libnative_bridge_guest_libOpenMAXAL",
    "libnative_bridge_guest_libOpenSLES",
    "libnative_bridge_guest_libvulkan",
    "libnative_bridge_guest_libwebviewchromium_plat_support",
];
const PROPERTIES: &[(&str, &str)] = &[
    ("ro.dalvik.vm.native.bridge", "libberberis_arm64.so"),
    ("ro.dalvik.vm.isa.arm64", "x86_64"),
    (
        "ro.vendor.droidloom.berberis.flags",
        "android-mmap-noreserve",
    ),
    // Stock init derives global CPU ABI properties from this vendor namespace.
    // The official product/odm partitions do not declare higher-priority lists.
    ("ro.vendor.product.cpu.abilist", "x86_64,arm64-v8a"),
    ("ro.vendor.product.cpu.abilist64", "x86_64,arm64-v8a"),
    ("ro.vendor.product.cpu.abilist32", ""),
];

#[derive(Clone, Copy, Debug)]
pub(super) enum Phase<'a> {
    Native,
    Vendor(&'a Bridge),
}
#[derive(Clone, Copy, Debug)]
pub(super) struct Request<'a> {
    pub inputs: &'a VerifiedVendorInputs,
    pub phase: Phase<'a>,
}
impl Request<'_> {
    pub fn targets(&self) -> &'static [&'static str] {
        match self.phase {
            Phase::Native => NATIVE_TARGETS,
            Phase::Vendor(_) => VENDOR_TARGETS,
        }
    }
    pub fn name(&self) -> &'static str {
        match self.phase {
            Phase::Native => "normal-native-distribution",
            Phase::Vendor(_) => "normal-vendor-image",
        }
    }
}

#[derive(Clone, Debug, Serialize)]
struct Artifact {
    path: PathBuf,
    bytes: u64,
    sha256: String,
    f9: [u64; 9],
}
fn f9(m: &fs::Metadata) -> Result<[u64; 9]> {
    let ns = |s: i64, n: i64| -> Result<u64> {
        Ok(u64::try_from(
            i128::from(s) * 1_000_000_000 + i128::from(n),
        )?)
    };
    Ok([
        m.dev(),
        m.ino(),
        m.mode() as u64,
        m.uid() as u64,
        m.gid() as u64,
        m.nlink(),
        m.len(),
        ns(m.mtime(), m.mtime_nsec())?,
        ns(m.ctime(), m.ctime_nsec())?,
    ])
}
fn artifact(path: &Path, limit: u64) -> Result<Artifact> {
    if !path.is_absolute() {
        return fail("official vendor artifact must be absolute");
    }
    for parent in path.ancestors().skip(1) {
        let m = fs::symlink_metadata(parent)?;
        if !m.is_dir() || m.file_type().is_symlink() {
            return fail("official vendor artifact parent alias");
        }
    }
    let m = fs::symlink_metadata(path)?;
    if !m.is_file()
        || m.file_type().is_symlink()
        || m.nlink() != 1
        || m.len() == 0
        || m.len() > limit
    {
        return fail("official vendor artifact must be a bounded single-link regular file");
    }
    let result = Artifact {
        path: path.into(),
        bytes: m.len(),
        sha256: hash(path)?,
        f9: f9(&m)?,
    };
    if result.f9 != f9(&fs::symlink_metadata(path)?)? {
        return fail("vendor artifact changed while hashed");
    }
    Ok(result)
}
impl Artifact {
    fn check(&self) -> Result<()> {
        let actual = artifact(&self.path, self.bytes)?;
        if actual.f9 != self.f9 || actual.sha256 != self.sha256 {
            return fail("normal vendor input was replaced or modified");
        }
        Ok(())
    }
}

#[derive(Debug)]
pub(super) struct Bridge {
    archive: Artifact,
    files: BTreeMap<String, Artifact>,
    host_needed: BTreeMap<String, Vec<String>>,
    qualification: Value,
}
fn vendor_path(original: &str) -> Result<String> {
    if let Some(name) = original.strip_prefix("system/lib64/") {
        if HOST_MODULES
            .iter()
            .any(|module| name == format!("{module}.so"))
        {
            return Ok(format!("{HOST_DIRECTORY}/{name}"));
        }
    }
    let guest = original
        .strip_prefix("system/")
        .ok_or("distribution outside system prefix")?;
    let path = Path::new(guest);
    if path
        .components()
        .any(|c| !matches!(c, std::path::Component::Normal(_)))
        || guest.contains('\\')
        || guest
            .bytes()
            .any(|c| !c.is_ascii_alphanumeric() && !b"/_-.+".contains(&c))
        || !(guest.starts_with("lib64/arm64/")
            || guest == "bin/arm64/linker64"
            || guest == "bin/arm64/app_process64")
    {
        return fail("unexpected file in the normal NativeBridge distribution");
    }
    Ok(format!("{GUEST_DIRECTORY}/{guest}"))
}

fn module_name(soname: &str) -> Result<String> {
    let name = soname
        .strip_suffix(".so")
        .ok_or("native dependency without shared-library suffix")?;
    if name.is_empty()
        || !name
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"_+.-".contains(&b))
    {
        return fail("invalid native dependency name");
    }
    Ok(format!(
        "droidloom_cp3a_vendor_{}",
        name.replace(['+', '.', '-'], "_")
    ))
}

#[derive(Clone, Debug)]
struct Elf {
    needed: Vec<String>,
    soname: Option<String>,
    imports: BTreeSet<String>,
    exports: BTreeSet<String>,
}
fn parse_symbols(text: &str) -> Result<(BTreeSet<String>, BTreeSet<String>)> {
    let mut imports = BTreeSet::new();
    let mut exports = BTreeSet::new();
    let mut saw_table = false;
    for line in text.lines() {
        if line.starts_with("Symbol table '.dynsym'") {
            saw_table = true;
        }
        let fields: Vec<_> = line.split_whitespace().collect();
        if fields.len() < 8
            || !fields[0].ends_with(':')
            || fields[0].trim_end_matches(':').parse::<u64>().is_err()
        {
            continue;
        }
        let name = fields[7];
        if fields[6] == "UND" {
            if fields[4] == "GLOBAL" {
                imports.insert(name.into());
            }
        } else if matches!(fields[4], "GLOBAL" | "WEAK" | "UNIQUE")
            && matches!(fields[5], "DEFAULT" | "PROTECTED")
        {
            if let Some((bare, version)) = name.split_once("@@") {
                exports.insert(bare.into());
                exports.insert(format!("{bare}@{version}"));
            } else {
                exports.insert(name.into());
            }
        }
    }
    if !saw_table {
        return fail("actual ELF dynamic symbol table missing");
    }
    Ok((imports, exports))
}
fn readelf_path() -> Result<PathBuf> {
    for directory in std::env::split_paths(&std::env::var_os("PATH").ok_or("build PATH missing")?) {
        let candidate = directory.join("readelf");
        if candidate.is_file() {
            let path = candidate.canonicalize()?;
            let metadata = fs::symlink_metadata(&path)?;
            if metadata.uid() != 0 || metadata.mode() & 0o022 != 0 {
                return fail("readelf must be a root-owned non-writable normal build tool");
            }
            return Ok(path);
        }
    }
    fail("normal build readelf is missing")
}
fn elf(path: &Path, machine: u16) -> Result<Elf> {
    let raw = fs::read(path)?;
    if raw.len() < 64
        || &raw[..6] != b"\x7fELF\x02\x01"
        || u16::from_le_bytes([raw[18], raw[19]]) != machine
    {
        return fail(format!(
            "wrong NativeBridge ELF architecture: {}",
            path.display()
        ));
    }
    let readelf = readelf_path()?;
    let dynamic = output(
        Command::new(&readelf)
            .args(["--dynamic", "--wide"])
            .arg(path),
    )?;
    let mut needed = Vec::new();
    let mut soname = None;
    for line in dynamic.lines() {
        if line.contains("(NEEDED)") || line.contains("(SONAME)") {
            let value = line
                .split_once('[')
                .and_then(|(_, s)| s.strip_suffix(']'))
                .ok_or("invalid ELF dynamic string")?;
            module_name(value)?;
            if line.contains("(NEEDED)") {
                needed.push(value.to_owned());
            } else if soname.replace(value.to_owned()).is_some() {
                return fail("duplicate ELF SONAME");
            }
        }
        if line.contains("(RPATH)") || line.contains("(RUNPATH)") {
            return fail("NativeBridge package contains an undeclared ELF search path");
        }
    }
    let symbols = output(
        Command::new(readelf)
            .args(["--dyn-syms", "--wide"])
            .arg(path),
    )?;
    let (imports, exports) = parse_symbols(&symbols)?;
    Ok(Elf {
        needed,
        soname,
        imports,
        exports,
    })
}

fn check_bridge(
    archive: &Path,
    destination: &Path,
    inputs: &VerifiedVendorInputs,
) -> Result<Bridge> {
    let archive = artifact(archive, 512 * 1024 * 1024)?;
    let listing = output(Command::new("unzip").arg("-Z1").arg(&archive.path))?;
    let mut names = BTreeSet::new();
    for name in listing.lines() {
        vendor_path(name)?;
        if !names.insert(name.to_owned()) || names.len() > 160 {
            return fail("duplicate or oversized NativeBridge package inventory");
        }
    }
    for module in HOST_MODULES {
        if !names.contains(&format!("system/lib64/{module}.so")) {
            return fail("normal distribution omitted a required host translator module");
        }
    }
    for name in [
        "system/lib64/arm64/libc.so",
        "system/lib64/arm64/libm.so",
        "system/lib64/arm64/libnative_bridge_vdso.so",
        "system/lib64/arm64/libdl.so",
        "system/bin/arm64/linker64",
        "system/bin/arm64/app_process64",
    ] {
        if !names.contains(name) {
            return fail("normal distribution omitted a required guest runtime file");
        }
    }
    fs::create_dir(destination)?;
    let mut files = BTreeMap::new();
    let mut total = 0;
    let deadline = Instant::now() + Duration::from_secs(180);
    for name in names {
        let target = destination.join(vendor_path(&name)?);
        fs::create_dir_all(target.parent().ok_or("bridge output parent")?)?;
        let file = fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&target)?;
        let mut child = Command::new("unzip")
            .arg("-p")
            .arg(&archive.path)
            .arg(&name)
            .stdin(Stdio::null())
            .stdout(Stdio::from(file))
            .stderr(Stdio::null())
            .spawn()?;
        let status = loop {
            if let Some(status) = child.try_wait()? {
                break status;
            }
            if Instant::now() >= deadline || fs::metadata(&target)?.len() > 64 * 1024 * 1024 {
                child.kill()?;
                child.wait()?;
                return fail("NativeBridge extraction exceeded its finite file/deadline bound");
            }
            std::thread::sleep(Duration::from_millis(10));
        };
        if !status.success() {
            return fail("normal NativeBridge archive member extraction failed");
        }
        let item = artifact(&target, 64 * 1024 * 1024)?;
        total += item.bytes;
        if total > 512 * 1024 * 1024 {
            return fail("NativeBridge distribution exceeds its total bound");
        }
        files.insert(name, item);
    }
    archive.check()?;
    let mut host = BTreeMap::new();
    let mut guest = BTreeMap::new();
    let mut guest_bytes = BTreeMap::new();
    for (name, item) in &files {
        let is_host = vendor_path(name)?.starts_with(HOST_DIRECTORY);
        let parsed = elf(&item.path, if is_host { 62 } else { 183 })?;
        let soname = parsed.soname.clone().unwrap_or_else(|| {
            Path::new(name)
                .file_name()
                .unwrap()
                .to_string_lossy()
                .into_owned()
        });
        if !is_host {
            if let Some(previous) = guest_bytes.insert(soname.clone(), item.sha256.clone()) {
                if previous != item.sha256 {
                    return fail("guest ELF SONAME has different providers");
                }
                continue;
            }
        }
        let map = if is_host { &mut host } else { &mut guest };
        if map.insert(soname, parsed).is_some() {
            return fail("duplicate NativeBridge ELF SONAME");
        }
    }
    let mut providers = host.clone();
    let mut api_inputs = BTreeSet::new();
    for parsed in host.values() {
        for dependency in &parsed.needed {
            if !host.contains_key(dependency) {
                api_inputs.insert(dependency.clone());
            }
        }
    }
    for soname in &api_inputs {
        let reference = inputs.reference_path(soname)?;
        let parsed = elf(reference, 62)?;
        if parsed.soname.as_ref() != Some(soname) {
            return fail("official reference SONAME differs from actual dependency");
        }
        providers.insert(soname.clone(), parsed);
    }
    let mut host_needed = BTreeMap::new();
    for (name, parsed) in &host {
        let mut provided = parsed.exports.clone();
        for dependency in &parsed.needed {
            provided.extend(
                providers
                    .get(dependency)
                    .ok_or("host DT_NEEDED has no exact provider")?
                    .exports
                    .clone(),
            );
        }
        let missing: Vec<_> = parsed.imports.difference(&provided).cloned().collect();
        if !missing.is_empty() {
            return fail(format!(
                "CP3A native imports are not supplied for {name}: {}",
                missing.join(", ")
            ));
        }
        host_needed.insert(name.clone(), parsed.needed.clone());
    }
    for (name, parsed) in &guest {
        for dep in &parsed.needed {
            if !guest.contains_key(dep) {
                return fail(format!("guest DT_NEEDED missing: {name} -> {dep}"));
            }
        }
    }
    inputs.verify_unchanged()?;
    let qualification = json!({"schema":"droidloom-cp3a-native-static-link-check-v1",
        "host_x86_64_libraries":host.len(),"guest_arm64_elfs":guest.len(),
        "official_api_providers":api_inputs,"host_direct_import_versions_supplied":true,
        "guest_dt_needed_supplied":true,"readelf":artifact(&readelf_path()?,64*1024*1024)?,
        "actual_native_bridge_callbacks_qualified":false,"linker_namespace_qualified":false,
        "runtime_qualified":false,"production_ready":false});
    Ok(Bridge {
        archive,
        files,
        host_needed,
        qualification,
    })
}

fn native_blueprint() -> String {
    format!(
        "package {{ default_applicable_licenses: [\"Android-Apache-2.0\"], }}\nndk_translation_package {{\n name: \"droidloom_cp3a_native_bridge_package\",\n compile_multilib: \"64\",\n native_bridge_supported: true,\n device_64_deps: {},\n native_bridge_deps: {},\n generate_build_files: false,\n}}\n",
        serde_json::to_string(HOST_MODULES).unwrap(),
        serde_json::to_string(GUEST_MODULES).unwrap()
    )
}
fn product_text(modules: &[String]) -> String {
    let mut s = String::from(
        "# Separate vendor for the exact official CP3A GSI.\ninclude frameworks/libs/binary_translation/berberis_config.mk\nPRODUCT_SOONG_NAMESPACES += frameworks/libs/native_bridge_support/android_api/libc\nBUILD_BERBERIS := true\nBUILD_BERBERIS_ARM64_TO_X86_64 := true\n$(call soong_config_set,berberis,translation_arch,arm64_to_x86_64)\nDROIDLOOM_NATIVE_BRIDGE_PACKAGES :=\n",
    );
    if !modules.is_empty() {
        s.push_str(&format!("PRODUCT_PACKAGES += {}\n", modules.join(" ")));
    }
    for (name, value) in PROPERTIES {
        s.push_str(&format!("PRODUCT_VENDOR_PROPERTIES += {name}={value}\n"));
    }
    s
}
fn guest_linker_config() -> &'static str {
    "# ARM64 interpreter input; the original CP3A host linker stays unchanged.\ndir.system = /vendor/etc/droidloom/nativebridge/guest\ndir.system = /data\ndir.system = /system\n[system]\nnamespace.default.visible = true\nnamespace.default.isolated = false\nnamespace.default.search.paths = /vendor/etc/droidloom/nativebridge/guest/${LIB}/arm64/bootstrap:/vendor/etc/droidloom/nativebridge/guest/${LIB}/arm64\nnamespace.default.permitted.paths = /vendor/etc/droidloom/nativebridge/guest/${LIB}/arm64\n"
}
fn exact_replace(
    path: &Path,
    expected: &str,
    old: &str,
    new: &str,
    count: usize,
    projection: &mut Projection,
) -> Result<()> {
    let raw = fs::read_to_string(path)?;
    if format!("{:x}", Sha256::digest(raw.as_bytes())) != expected
        || raw.matches(old).count() != count
    {
        return fail(format!(
            "official vendor source projection does not match its exact source: {}",
            path.display()
        ));
    }
    projection.put(path, raw.replace(old, new))
}

pub(super) fn project(
    source: &Path,
    vendor: &Path,
    request: Request<'_>,
    projection: &mut Projection,
) -> Result<()> {
    request.inputs.verify_unchanged()?;
    exact_replace(
        &source.join("frameworks/libs/binary_translation/guest_loader/guest_loader.cc"),
        "66914c503389c81627bd2751b328535592138e517dce1ed36bf9468c5c46a397",
        "std::filesystem::path result(\"/system\");",
        "std::filesystem::path result(\"/vendor/etc/droidloom/nativebridge/guest\");",
        1,
        projection,
    )?;
    exact_replace(
        &source.join(
            "frameworks/libs/binary_translation/runtime_primitives/exec_region_elf_backed.cc",
        ),
        "92fc166e0d5fc08dec68514b19840d85290b29423dd9f7e9661b489f52695337",
        "/system/lib64/libberberis_exec_region.so",
        &format!("/vendor/{HOST_DIRECTORY}/libberberis_exec_region.so"),
        1,
        projection,
    )?;
    // Proxy names originate from translated guest symbols. Require a leaf before
    // joining the sealed host-side distribution directory.
    exact_replace(
        &source.join("frameworks/libs/binary_translation/proxy_loader/proxy_loader.cc"),
        "f1f6331f766e52b10bc65b3a6c866181a1dcee58bdc1a8281ddadacfaa98da46",
        "  proxy_name += library_name;",
        &format!(
            "  proxy_name += library_name;\n  if (proxy_name.find('/') != std::string::npos) return false;\n  proxy_name.insert(0, \"/vendor/{HOST_DIRECTORY}/\");"
        ),
        1,
        projection,
    )?;
    exact_replace(
        &source.join("frameworks/libs/binary_translation/base/config_globals.cc"),
        "0cf75cdbc4a94460b1cc0c5d8303ffc5ffab78fd9df8eb88d211551e587d6c18",
        "\"ro.berberis.flags\"",
        "\"ro.vendor.droidloom.berberis.flags\"",
        1,
        projection,
    )?;
    exact_replace(
        &source.join(
            "frameworks/libs/native_bridge_support/android_api/linker/linker_translate_path.cpp",
        ),
        "c881d98f4867ebc1d991022f772ae3fd8057b886b882636737ae6269ba3a51e8",
        "\"/system/lib64/arm64/\"",
        "\"/vendor/etc/droidloom/nativebridge/guest/lib64/arm64/\"",
        2,
        projection,
    )?;
    exact_replace(
        &source.join("bionic/linker/linker.cpp"),
        "b7bf38b2f8a3708c42e57bebd5844a40fc1afcac6929d1aaa183c22a7568016b",
        "static const char* const kLdConfigArchFilePath = \"/system/etc/ld.config.\" ABI_STRING \".txt\";",
        "// This x86_64-only source product builds ARM64 solely as interpreter input.\n#if defined(__aarch64__)\nstatic const char* const kLdConfigArchFilePath = \"/vendor/etc/droidloom/nativebridge/guest/etc/ld.config.arm64.txt\";\n#else\nstatic const char* const kLdConfigArchFilePath = \"/system/etc/ld.config.\" ABI_STRING \".txt\";\n#endif",
        1,
        projection,
    )?;
    let pack = vendor.join("android/native-bridge/official-vendor");
    fs::create_dir_all(&pack)?;
    let modules = match request.phase {
        Phase::Native => {
            projection.put(&pack.join("Android.bp"), native_blueprint())?;
            Vec::new()
        }
        Phase::Vendor(bridge) => stage_vendor_modules(&pack, request.inputs, bridge, projection)?,
    };
    projection.put(
        &vendor.join("android/native-bridge/product.mk"),
        product_text(&modules),
    )?;
    let board = vendor.join("android/device/droidloom_x86_64/BoardConfig.mk");
    projection.put(&board, fs::read_to_string(&board)? + "\nBOARD_VENDOR_SEPOLICY_DIRS += vendor/droidloom/android/native-bridge/official-vendor/sepolicy\n")?;
    projection.put(&pack.join("sepolicy/file_contexts"), VENDOR_FILE_CONTEXTS)?;
    projection.put(&pack.join("sepolicy/property.te"),
        "vendor_public_prop(droidloom_native_bridge_config_prop)\nset_prop(vendor_init, droidloom_native_bridge_config_prop)\nget_prop({ appdomain zygote }, droidloom_native_bridge_config_prop)\n")?;
    projection.put(&pack.join("sepolicy/property_contexts"),
        "ro.vendor.droidloom.berberis.flags u:object_r:droidloom_native_bridge_config_prop:s0 exact string\n")?;
    Ok(())
}

fn stage_vendor_modules(
    pack: &Path,
    inputs: &VerifiedVendorInputs,
    bridge: &Bridge,
    projection: &mut Projection,
) -> Result<Vec<String>> {
    bridge.archive.check()?;
    let mut bp =
        String::from("package { default_applicable_licenses: [\"Android-Apache-2.0\"], }\n");
    let mut modules = Vec::new();
    let mut api = BTreeSet::new();
    for (original, item) in &bridge.files {
        item.check()?;
        let installed = vendor_path(original)?;
        let relative = format!("payload/{installed}");
        projection.put(&pack.join(&relative), fs::read(&item.path)?)?;
        let path = Path::new(&installed);
        let name = path
            .file_name()
            .ok_or("native output name")?
            .to_str()
            .ok_or("native output UTF8")?;
        if installed.starts_with(HOST_DIRECTORY) {
            let module = module_name(name)?;
            let deps = bridge
                .host_needed
                .get(name)
                .ok_or("native output dependency inventory")?;
            let mut dep_modules = Vec::new();
            for dep in deps {
                if bridge.host_needed.contains_key(dep) {
                    dep_modules.push(module_name(dep)?);
                } else {
                    api.insert(dep.clone());
                    dep_modules.push(format!("{}_reference", module_name(dep)?));
                }
            }
            bp.push_str(&format!("cc_prebuilt_library_shared {{\n name: {module:?}, stem: {:?}, srcs: [{relative:?}],\n vendor: true, compile_multilib: \"64\", relative_install_path: \"droidloom/nativebridge\",\n system_shared_libs: [], shared_libs: {}, check_elf_files: true, strip: {{ none: true }},\n}}\n",
                name.trim_end_matches(".so"),serde_json::to_string(&dep_modules)?));
            modules.push(module);
        } else {
            // ARM64 files are inputs consumed by the interpreter, never host ELF providers.
            let module = format!("droidloom_cp3a_guest_{}", modules.len());
            let subdir = path
                .parent()
                .ok_or("guest parent")?
                .strip_prefix("etc")?
                .to_str()
                .ok_or("guest path UTF8")?;
            bp.push_str(&format!("prebuilt_etc {{ name: {module:?}, vendor: true, src: {relative:?}, filename: {name:?}, relative_install_path: {subdir:?}, }}\n"));
            modules.push(module);
        }
    }
    for name in api {
        let relative = format!("api/{name}");
        let source = inputs.reference_path(&name)?;
        projection.put(&pack.join(&relative), fs::read(source)?)?;
        let module = format!("{}_reference", module_name(&name)?);
        // These reviewed libraries are external link references only. The shipped
        // translator above retains normal ELF checks against their exact symbols.
        bp.push_str(&format!("cc_prebuilt_library_shared {{ name: {module:?}, stem: {:?}, srcs: [{relative:?}], vendor: true, compile_multilib: \"64\", installable: false, system_shared_libs: [], shared_libs: [], check_elf_files: false, strip: {{ none: true }}, }}\n",name.trim_end_matches(".so")));
    }
    projection.put(
        &pack.join("guest-ld.config.arm64.txt"),
        guest_linker_config(),
    )?;
    bp.push_str("prebuilt_etc { name: \"droidloom_cp3a_guest_linker_config\", vendor: true, src: \"guest-ld.config.arm64.txt\", filename: \"ld.config.arm64.txt\", relative_install_path: \"droidloom/nativebridge/guest/etc\", }\n");
    modules.push("droidloom_cp3a_guest_linker_config".into());
    projection.put(&pack.join("Android.bp"), bp)?;
    inputs.verify_unchanged()?;
    Ok(modules)
}

pub(super) fn input_receipt(out: &Path, request: Request<'_>) -> Result<()> {
    let mut receipt = serde_json::to_value(request.inputs.receipt()?)?;
    receipt["phase"] = request.name().into();
    receipt["requested_targets"] = json!(request.targets());
    receipt["source_lock"] =
        json!({"path":production_source::LOCK_PATH,"sha256":production_source::LOCK_SHA});
    receipt["source_release"] = PRODUCTION_TARGET_RELEASE.into();
    receipt["build_variant"] = PRODUCTION_BUILD_VARIANT.into();
    receipt["strict_allow_missing_dependencies"] = "false".into();
    receipt["selinux_ignore_neverallows"] = "false".into();
    receipt["source_revision_equivalence_claimed"] = false.into();
    receipt["host_library_search_directory"] = format!("/vendor/{HOST_DIRECTORY}").into();
    receipt["guest_interpreter_root"] = format!("/vendor/{GUEST_DIRECTORY}").into();
    if let Phase::Vendor(bridge) = request.phase {
        receipt["native_distribution"] = serde_json::to_value(&bridge.archive)?;
        receipt["native_files"] = serde_json::to_value(&bridge.files)?;
        receipt["native_static_link_check"] = bridge.qualification.clone();
    }
    write(&out.join(INPUT_NAME), serde_json::to_vec_pretty(&receipt)?)
}

pub(super) fn build(
    repo: &Path,
    source: &Path,
    out: &Path,
    work: &Path,
    product: &str,
    jobs: usize,
    inputs: &VerifiedVendorInputs,
) -> Result<()> {
    inputs.verify_unchanged()?;
    crate::native_generation_art::validated_output(work, out)?;
    fs::create_dir(out)?;
    write(
        &out.join("official-vendor-attempt.json"),
        serde_json::to_vec_pretty(&json!({
        "schema":"droidloom-official-gsi-independent-vendor-attempt-v1",
        "system_sha256":SYSTEM_SHA256,"reference_profile_sha256":PROFILE_SHA256,
        "source_release":PRODUCTION_TARGET_RELEASE,"variant":PRODUCTION_BUILD_VARIANT,
        "normal_phases":[NATIVE_TARGETS,VENDOR_TARGETS],"runtime_qualified":false,"production_ready":false}))?,
    )?;
    crate::assemble::prepare_vendor_build_tools(repo, work, jobs)?;
    let native = out.join("native");
    build_targets_with_fixed_request(
        repo,
        source,
        &native,
        work,
        product,
        jobs,
        FixedProductionRequest::OfficialGsiVendor(Request {
            inputs,
            phase: Phase::Native,
        }),
    )?;
    inputs.verify_unchanged()?;
    let archive = native.join("soong/.intermediates/vendor/droidloom/android/native-bridge/official-vendor/droidloom_cp3a_native_bridge_package/android_common/droidloom_cp3a_native_bridge_package.zip");
    let bridge = check_bridge(&archive, &out.join("native-vendor-inputs"), inputs)?;
    let vendor_out = out.join("vendor");
    build_targets_with_fixed_request(
        repo,
        source,
        &vendor_out,
        work,
        product,
        jobs,
        FixedProductionRequest::OfficialGsiVendor(Request {
            inputs,
            phase: Phase::Vendor(&bridge),
        }),
    )?;
    inputs.verify_unchanged()?;
    bridge.archive.check()?;
    let product_out = vendor_out.join("target/product").join(product);
    let vendor = product_out.join("vendor");
    let observed: BTreeMap<String, String> = fs::read_to_string(vendor.join("build.prop"))?
        .lines()
        .filter(|l| !l.starts_with('#'))
        .filter_map(|l| l.split_once('='))
        .map(|(k, v)| (k.into(), v.into()))
        .collect();
    for (name, value) in PROPERTIES {
        if observed.get(*name).map(String::as_str) != Some(*value) {
            return fail("normal vendor omitted its required NativeBridge property");
        }
    }
    let mut actual = BTreeMap::new();
    for (original, item) in &bridge.files {
        let path = vendor.join(vendor_path(original)?);
        let installed = artifact(&path, item.bytes)?;
        if installed.sha256 != item.sha256 {
            return fail("normal vendor changed a checked NativeBridge binary");
        }
        actual.insert(vendor_path(original)?, installed);
    }
    let vendor_image = artifact(&product_out.join("vendor.img"), 2 * 1024 * 1024 * 1024)?;
    let graphics_hal_entries =
        crate::coherent_images::verify_vendor_graphics_hal_entries(&product_out)?;
    vendor_image.check()?;
    let record = json!({"schema":"droidloom-official-gsi-independent-vendor-normal-result-v1",
        "official_inputs":inputs.receipt()?,"native_build_inputs":artifact(&native.join(INPUT_NAME),16*1024*1024)?,
        "vendor_build_inputs":artifact(&vendor_out.join(INPUT_NAME),16*1024*1024)?,
        "normal_vendor_result":artifact(&vendor_out.join("droidloom-production-full653-vendor-normal-result.json"),64*1024*1024)?,
        "normal_vendor_image":vendor_image,
        "graphics_hal_image_entrypoints":graphics_hal_entries,
        "host_checkvintf":artifact(&vendor_out.join("host/linux-x86/bin/checkvintf"),128*1024*1024)?,
        "native_binaries":actual,"native_static_link_check":bridge.qualification,
        "official_system_bytes_preserved":true,"normal_user_commands_returned_success":true,
        "source_projection_restored":true,"source_release":PRODUCTION_TARGET_RELEASE,
        "source_revision_equivalence_qualified":false,"linker_namespace_qualified":false,
        "selected_CP3A_policy_qualified":false,"kernel_vintf_qualified":false,
        "production_signing_qualified":false,"runtime_qualified":false,"production_ready":false});
    write(&out.join(RESULT_NAME), serde_json::to_vec_pretty(&record)?)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn vendor_mapping_refuses_system_replacement_and_path_escape() {
        assert_eq!(
            vendor_path("system/lib64/libberberis_arm64.so").unwrap(),
            "lib64/droidloom/nativebridge/libberberis_arm64.so"
        );
        assert_eq!(
            vendor_path("system/lib64/libberberis_exec_region.so").unwrap(),
            format!("{HOST_DIRECTORY}/libberberis_exec_region.so")
        );
        assert_eq!(
            vendor_path("system/lib64/arm64/libc.so").unwrap(),
            "etc/droidloom/nativebridge/guest/lib64/arm64/libc.so"
        );
        for bad in [
            "system/lib64/libc.so",
            "system/apex/com.android.art.apex",
            "system/lib64/arm64/../../libc.so",
            "system/bin/berberis_program_runner_binfmt_misc_arm64",
            "/system/lib64/arm64/libc.so",
        ] {
            assert!(vendor_path(bad).is_err(), "{bad}");
        }
    }
    #[test]
    fn symbol_versions_remain_distinct_and_weak_imports_are_optional() {
        let text = "Symbol table '.dynsym' contains 5 entries:\n 1: 000 0 FUNC GLOBAL DEFAULT UND api@V2 (2)\n 2: 000 0 FUNC WEAK DEFAULT UND optional\n 3: 001 2 FUNC GLOBAL DEFAULT 7 api@@V1\n 4: 002 2 FUNC GLOBAL DEFAULT 7 plain\n";
        let (imports, exports) = parse_symbols(text).unwrap();
        assert!(imports.contains("api@V2"));
        assert!(!imports.contains("optional"));
        assert!(
            exports.contains("api@V1") && exports.contains("api") && !exports.contains("api@V2")
        );
        assert!(parse_symbols("not readelf").is_err());
    }
    #[test]
    fn product_uses_vendor_properties_and_no_global_binfmt_registration() {
        let p = product_text(&["one_checked_vendor_module".into()]);
        assert!(p.contains(
            "PRODUCT_VENDOR_PROPERTIES += ro.dalvik.vm.native.bridge=libberberis_arm64.so"
        ));
        assert!(!p.contains("PRODUCT_SYSTEM_PROPERTIES"));
        assert!(!native_blueprint().contains("binfmt"));
        let executable_roots: Vec<_> = guest_linker_config()
            .lines()
            .take_while(|line| *line != "[system]")
            .filter_map(|line| line.strip_prefix("dir.system = "))
            .collect();
        assert_eq!(
            executable_roots,
            [
                "/vendor/etc/droidloom/nativebridge/guest",
                "/data",
                "/system"
            ]
        );
    }
}
