//! Fixed native v2 input production. ELF bytes and effective configuration are
//! observed; symbol-surface comparison is explicitly not a C++ ABI/live proof.
#[path = "../../../../runtime/droidloom-supervisor/src/production_native_build_evidence.rs"]
mod build_evidence;
use crate::contract::{
    Adapter, BuildPlan, FileRef, ImageDeclaration, MAX_CONFIG, MAX_PLAN, absolute,
};
use crate::io::{self, Deadline, Inputs, Runner};
use crate::{Result, require};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

const MAX_ELF: u64 = 4 * 1024 * 1024; // Matches the fixed debugfs cat stdout bound.
const WEIGHTS: [u32; 11] = [100, 20, 100, 50, 100, 100, 200, 200, 100, 100, 20];
const CPU_CLASSES: [&str; 11] = [
    "default",
    "background",
    "system",
    "system-background",
    "foreground",
    "foreground_window",
    "top-app",
    "rt",
    "camera-daemon",
    "nnapi-hal",
    "dex2oat",
];
const SET_CLASSES: [&str; 14] = [
    "",
    "system/background",
    "system",
    "system/performance",
    "application/background",
    "application",
    "application/performance",
    "background",
    "foreground",
    "foreground_window",
    "top-app",
    "system-background",
    "restricted",
    "camera-daemon",
];
const SET_ROLES: [&str; 14] = [
    "normal", "little", "normal", "graphics", "little", "normal", "graphics", "little", "normal",
    "normal", "graphics", "little", "little", "normal",
];

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct NativeInput {
    pub schema: String,
    pub original_elf: FileRef,
    pub derived_elf: FileRef,
    pub original_setup_elf: FileRef,
    pub derived_setup_elf: FileRef,
    pub build_provenance: FileRef,
    pub placement_provenance: FileRef,
    pub first_api_level: u32,
    pub normal_cpus: String,
    pub little_cpus: String,
    pub graphics_cpus: String,
    pub mems: String,
    pub dependencies: Vec<DependencyInput>,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct DependencyInput {
    image_role: String,
    image_path: String,
    guest_path: String,
    elf: FileRef,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct BuildProvenance {
    schema: String,
    source_basis: String,
    source_system_sha256: String,
    original_elf_sha256: String,
    derived_elf_sha256: String,
    original_setup_elf_sha256: String,
    derived_setup_elf_sha256: String,
    source_manifest: FileRef,
    toolchain_manifest: FileRef,
    actual_build_result: FileRef,
    actual_retirement: FileRef,
    actual_abi_result: FileRef,
    actual_abi_tables: FileRef,
}
#[derive(Debug, Serialize)]
pub(crate) struct NativeDeclaration {
    pub scope: &'static str,
    pub source_system_sha256: String,
    pub original_elf_sha256: String,
    pub original_elf_bytes: u64,
    pub original_build_id: String,
    pub derived_build_id: String,
    pub library: ImageDeclaration,
    pub original_setup_elf_sha256: String,
    pub original_setup_elf_bytes: u64,
    pub original_setup_build_id: String,
    pub derived_setup_build_id: String,
    pub setup_library: ImageDeclaration,
    pub policy: ImageDeclaration,
    pub source_provenance_sha256: String,
    pub effective_inputs_sha256: String,
    pub abi_surface_sha256: String,
    pub source_basis: String,
    pub native_execution_qualified: bool,
    pub build_evidence: build_evidence::Receipt,
    pub unsupported_effective_profiles: Vec<String>,
    pub unsupported_rc_actions: Vec<String>,
}
#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
struct Symbol {
    name: String,
    kind: u8,
    binding: u8,
    visibility: u8,
    // Function code size is not an ABI invariant. Object/TLS size is.
    data_bytes: Option<u64>,
}
#[derive(Debug, Serialize)]
struct Elf {
    build_id: String,
    soname: String,
    needed: Vec<String>,
    exports: BTreeMap<String, Symbol>,
    required_imports: BTreeSet<String>,
    version_sections: BTreeMap<u32, String>,
}
fn slice(raw: &[u8], offset: u64, bytes: u64) -> Result<&[u8]> {
    let end = offset.checked_add(bytes).ok_or("ELF range overflow")?;
    require(end <= raw.len() as u64, "ELF range escapes actual body")?;
    Ok(&raw[offset as usize..end as usize])
}
fn u16le(v: &[u8], n: usize) -> u16 {
    u16::from_le_bytes(v[n..n + 2].try_into().unwrap())
}
fn u32le(v: &[u8], n: usize) -> u32 {
    u32::from_le_bytes(v[n..n + 4].try_into().unwrap())
}
fn u64le(v: &[u8], n: usize) -> u64 {
    u64::from_le_bytes(v[n..n + 8].try_into().unwrap())
}
fn string(table: &[u8], offset: u64) -> Result<String> {
    let start = usize::try_from(offset)?;
    let tail = table.get(start..).ok_or("ELF string offset")?;
    let end = tail
        .iter()
        .position(|&b| b == 0)
        .ok_or("ELF unterminated string")?;
    require(end <= 4096, "bounded ELF string")?;
    Ok(std::str::from_utf8(&tail[..end])?.to_owned())
}
fn library_name(s: &str) -> bool {
    !s.is_empty()
        && s.len() <= 160
        && s.ends_with(".so")
        && s.bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"._+-".contains(&b))
        && !s.contains("..")
}
fn dependency_location(image_role: &str, image_path: &str, guest_path: &str, soname: &str) -> bool {
    // The original runtime APEX loader deliberately has a SONAME unlike its
    // executable basename. This is one fixed source role, not a general alias.
    if image_role == "apex:com.android.runtime"
        && image_path == "/bin/linker64"
        && guest_path == "/apex/com.android.runtime/bin/linker64"
    {
        soname == "ld-android.so"
    } else {
        guest_path.contains("/lib64/")
            && Path::new(guest_path).file_name().and_then(|n| n.to_str()) == Some(soname)
    }
}
fn elf(raw: &[u8]) -> Result<Elf> {
    require(
        raw.len() >= 64 && raw.len() as u64 <= MAX_ELF,
        "bounded ELF header",
    )?;
    require(
        &raw[..7] == b"\x7fELF\x02\x01\x01"
            && u16le(raw, 16) == 3
            && u16le(raw, 18) == 62
            && u32le(raw, 20) == 1
            && u16le(raw, 52) == 64
            && u16le(raw, 54) == 56
            && u16le(raw, 58) == 64,
        "actual x86_64 little-endian shared ELF",
    )?;
    let phnum = u16le(raw, 56) as u64;
    let shnum = u16le(raw, 60) as usize;
    require(
        (1..=128).contains(&phnum) && (1..=2048).contains(&shnum),
        "ELF header-count bounds",
    )?;
    let program = slice(raw, u64le(raw, 32), phnum * 56)?;
    let sections = slice(raw, u64le(raw, 40), shnum as u64 * 64)?;
    let mut loads = Vec::new();
    let mut dynamic = None;
    let mut stack_nx = false;
    for p in program.chunks_exact(56) {
        let kind = u32le(p, 0);
        let flags = u32le(p, 4);
        let offset = u64le(p, 8);
        let filesz = u64le(p, 32);
        let memsz = u64le(p, 40);
        slice(raw, offset, filesz)?;
        require(
            kind != 3,
            "a fixed DSO must not have a PT_INTERP executable entry",
        )?;
        if kind == 1 {
            require(
                filesz <= memsz && flags & 3 != 3,
                "bounded non-WX load segment",
            )?;
            require(
                u64le(p, 16).checked_add(memsz).is_some(),
                "DSO load address overflow",
            )?;
            loads.push((offset, filesz, flags, u64le(p, 16)));
        }
        if kind == 2 {
            require(
                dynamic.replace((offset, filesz)).is_none(),
                "one PT_DYNAMIC",
            )?;
        }
        if kind == 0x6474e551 {
            require(!stack_nx && flags & 1 == 0, "one nonexecutable GNU stack")?;
            stack_nx = true;
        }
    }
    require(
        stack_nx && loads.iter().any(|p| p.2 & 1 != 0 && p.1 > 0),
        "actual executable DSO segment and NX stack",
    )?;
    let sh: Vec<_> = sections.chunks_exact(64).collect();
    let mut build_id = None;
    let mut dynsym = None;
    let mut dynsection = None;
    let mut versions = BTreeMap::new();
    for (index, s) in sh.iter().enumerate() {
        let kind = u32le(s, 4);
        let offset = u64le(s, 24);
        let bytes = u64le(s, 32);
        if kind == 8 {
            continue;
        }
        let body = slice(raw, offset, bytes)?;
        if kind == 7 {
            let mut at = 0usize;
            while at < body.len() {
                require(body.len() - at >= 12, "complete ELF note header")?;
                let name = u32le(body, at) as usize;
                let desc = u32le(body, at + 4) as usize;
                let ty = u32le(body, at + 8);
                let name_at = at + 12;
                let desc_at = name_at.checked_add((name + 3) & !3).ok_or("note range")?;
                let end = desc_at.checked_add((desc + 3) & !3).ok_or("note range")?;
                require(end <= body.len(), "complete ELF note body")?;
                if name == 4 && &body[name_at..name_at + 4] == b"GNU\0" && ty == 3 {
                    require(
                        (16..=64).contains(&desc) && build_id.is_none(),
                        "one full GNU Build ID",
                    )?;
                    build_id = Some(hex::encode(&body[desc_at..desc_at + desc]));
                }
                at = end;
            }
        }
        if kind == 11 {
            require(dynsym.replace(index).is_none(), "one dynamic symbol table")?;
        }
        if kind == 6 {
            require(
                dynsection.replace(index).is_none() && dynamic == Some((offset, bytes)),
                "matching dynamic section/segment",
            )?;
        }
        if [0x6fffffff, 0x6ffffffd, 0x6ffffffe].contains(&kind) {
            require(
                versions.insert(kind, io::hash(body)).is_none(),
                "unique GNU version section",
            )?;
        }
    }
    let dyn_index = dynsection.ok_or("actual dynamic section")?;
    let s = sh[dyn_index];
    let link = u32le(s, 40) as usize;
    require(
        link < sh.len() && u32le(sh[link], 4) == 3 && u64le(s, 56) == 16 && u64le(s, 32) % 16 == 0,
        "dynamic string/table format",
    )?;
    let strtab = slice(raw, u64le(sh[link], 24), u64le(sh[link], 32))?;
    let mut soname = None;
    let mut needed = Vec::new();
    let mut ended = false;
    let mut addressing = BTreeMap::new();
    for v in slice(raw, u64le(s, 24), u64le(s, 32))?.chunks_exact(16) {
        let tag = u64le(v, 0);
        let value = u64le(v, 8);
        if ended {
            require(tag == 0 && value == 0, "zero dynamic padding")?;
            continue;
        }
        if tag == 0 {
            ended = true;
            continue;
        }
        require(
            tag != 22 && (tag != 30 || value & 4 == 0),
            "no text relocations",
        )?;
        require(
            ![15, 29].contains(&tag),
            "no unmodeled DSO RPATH/RUNPATH search roots",
        )?;
        if [5, 6, 10, 11].contains(&tag) {
            require(
                addressing.insert(tag, value).is_none(),
                "unique dynamic address/size tag",
            )?;
        }
        if tag == 1 {
            let name = string(strtab, value)?;
            require(library_name(&name), "fixed needed library name")?;
            needed.push(name);
        }
        if tag == 14 {
            require(
                soname.replace(string(strtab, value)?).is_none(),
                "one DSO soname",
            )?;
        }
    }
    require(
        ended && needed.len() <= 64 && needed.iter().collect::<BTreeSet<_>>().len() == needed.len(),
        "complete bounded unique dependencies",
    )?;
    let sy = sh[dynsym.ok_or("actual dynamic symbols")?];
    let symbols_link = u32le(sy, 40) as usize;
    require(
        symbols_link == link
            && u64le(sy, 56) == 24
            && u64le(sy, 32) % 24 == 0
            && u64le(sy, 32) / 24 <= 65536,
        "bounded dynamic symbols",
    )?;
    let mapped = |address: u64, length: u64| -> Result<u64> {
        let mut matches = Vec::new();
        for &(offset, bytes, _, virtual_address) in &loads {
            if let Some(relative) = address.checked_sub(virtual_address) {
                if relative.checked_add(length).is_some_and(|end| end <= bytes) {
                    matches.push(offset + relative);
                }
            }
        }
        require(
            matches.len() == 1,
            "unique file-backed dynamic address mapping",
        )?;
        Ok(matches[0])
    };
    require(
        addressing.get(&10) == Some(&u64le(sh[link], 32))
            && addressing.get(&11) == Some(&24)
            && mapped(
                *addressing.get(&5).ok_or("DT_STRTAB absent")?,
                u64le(sh[link], 32),
            )? == u64le(sh[link], 24)
            && mapped(
                *addressing.get(&6).ok_or("DT_SYMTAB absent")?,
                u64le(sy, 32),
            )? == u64le(sy, 24),
        "symbol/string sections are the actual dynamic loader tables",
    )?;
    let mut exports = BTreeMap::new();
    let mut imports = BTreeSet::new();
    for sym in slice(raw, u64le(sy, 24), u64le(sy, 32))?.chunks_exact(24) {
        let binding = sym[4] >> 4;
        let kind = sym[4] & 15;
        let visibility = sym[5] & 3;
        if ![1, 2, 10].contains(&binding) {
            continue;
        }
        let name = string(strtab, u32le(sym, 0) as u64)?;
        if name.is_empty() {
            continue;
        }
        if u16le(sym, 6) == 0 {
            if binding == 1 {
                imports.insert(name);
            }
            continue;
        }
        if ![0, 3].contains(&visibility) {
            continue;
        }
        let value = Symbol {
            name: name.clone(),
            kind,
            binding,
            visibility,
            data_bytes: matches!(kind, 1 | 6).then(|| u64le(sym, 16)),
        };
        require(
            exports.insert(name, value).is_none(),
            "unique exposed dynamic symbol name",
        )?;
    }
    let soname = soname.ok_or("actual DSO soname")?;
    require(library_name(&soname), "safe actual soname")?;
    Ok(Elf {
        build_id: build_id.ok_or("actual Build ID")?,
        soname,
        needed,
        exports,
        required_imports: imports,
        version_sections: versions,
    })
}

fn mask(value: &str) -> Result<BTreeSet<u32>> {
    let mut result = BTreeSet::new();
    for part in value.split(',') {
        let (a, b) = match part.split_once('-') {
            Some((a, b)) => (a.parse::<u32>()?, b.parse::<u32>()?),
            None => {
                let n = part.parse()?;
                (n, n)
            }
        };
        require(a <= b && b < 4096, "bounded placement mask")?;
        for n in a..=b {
            require(result.insert(n), "unique placement CPU")?;
        }
    }
    require(!result.is_empty(), "nonempty placement mask")?;
    let mut ranges = Vec::new();
    let mut it = result.iter().copied().peekable();
    while let Some(first) = it.next() {
        let mut last = first;
        while it.peek() == Some(&(last + 1)) {
            last = it.next().ok_or("mask iterator")?;
        }
        ranges.push(if first == last {
            first.to_string()
        } else {
            format!("{first}-{last}")
        });
    }
    require(ranges.join(",") == value, "canonical placement mask")?;
    Ok(result)
}
fn debug(
    inputs: &Inputs,
    runner: &mut Runner<'_>,
    plan: &BuildPlan,
    image: &FileRef,
    command: &str,
) -> Result<Vec<u8>> {
    Ok(runner
        .run(
            inputs,
            &plan.tools.debugfs,
            &[
                "-R".into(),
                command.into(),
                inputs.descriptor_path(image)?.into_os_string(),
            ],
        )?
        .0)
}
// Exact absence is obtained by walking real directory listings. A tool's empty
// output or diagnostic substring never becomes an absent-input witness.
fn image_optional(
    inputs: &Inputs,
    runner: &mut Runner<'_>,
    plan: &BuildPlan,
    image: &FileRef,
    path: &str,
) -> Result<Option<Vec<u8>>> {
    absolute(Path::new(path))?;
    let parts: Vec<_> = path.trim_start_matches('/').split('/').collect();
    require(
        !parts.is_empty() && parts.len() <= 8,
        "fixed bounded image path",
    )?;
    let mut parent = String::from("/");
    for (index, part) in parts.iter().enumerate() {
        let rows = crate::image::listing(&debug(
            inputs,
            runner,
            plan,
            image,
            &format!("ls -l -p \"{parent}\""),
        )?)?;
        let Some((_, mode, _, _)) = rows.get(*part) else {
            return Ok(None);
        };
        let final_part = index + 1 == parts.len();
        require(
            mode & 0o170000 == if final_part { 0o100000 } else { 0o040000 },
            "image path is not a regular file through real directories",
        )?;
        if parent != "/" {
            parent.push('/');
        }
        parent.push_str(part);
    }
    let body = debug(inputs, runner, plan, image, &format!("cat \"{path}\""))?;
    require(
        !body.is_empty() && body.len() as u64 <= MAX_ELF,
        "actual bounded image file",
    )?;
    Ok(Some(body))
}
// Reject duplicate keys at every depth. A manifest's whole hash is not a
// substitute for unambiguous parsing of a configuration used by two parsers.
fn unique_json(raw: &[u8]) -> Result<Value> {
    struct Unique(Value);
    impl<'de> Deserialize<'de> for Unique {
        fn deserialize<D: serde::Deserializer<'de>>(d: D) -> std::result::Result<Self, D::Error> {
            struct V;
            impl<'de> serde::de::Visitor<'de> for V {
                type Value = Unique;
                fn expecting(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
                    f.write_str("unambiguous JSON")
                }
                fn visit_bool<E: serde::de::Error>(
                    self,
                    v: bool,
                ) -> std::result::Result<Unique, E> {
                    Ok(Unique(v.into()))
                }
                fn visit_i64<E: serde::de::Error>(self, v: i64) -> std::result::Result<Unique, E> {
                    Ok(Unique(v.into()))
                }
                fn visit_u64<E: serde::de::Error>(self, v: u64) -> std::result::Result<Unique, E> {
                    Ok(Unique(v.into()))
                }
                fn visit_f64<E: serde::de::Error>(self, _: f64) -> std::result::Result<Unique, E> {
                    Err(E::custom("floating-point configuration is unsupported"))
                }
                fn visit_str<E: serde::de::Error>(self, v: &str) -> std::result::Result<Unique, E> {
                    Ok(Unique(v.into()))
                }
                fn visit_string<E: serde::de::Error>(
                    self,
                    v: String,
                ) -> std::result::Result<Unique, E> {
                    Ok(Unique(v.into()))
                }
                fn visit_unit<E: serde::de::Error>(self) -> std::result::Result<Unique, E> {
                    Ok(Unique(Value::Null))
                }
                fn visit_seq<A: serde::de::SeqAccess<'de>>(
                    self,
                    mut a: A,
                ) -> std::result::Result<Unique, A::Error> {
                    let mut values = Vec::new();
                    while let Some(Unique(v)) = a.next_element::<Unique>()? {
                        if values.len() >= 4096 {
                            return Err(serde::de::Error::custom("bounded configuration array"));
                        }
                        values.push(v);
                    }
                    Ok(Unique(Value::Array(values)))
                }
                fn visit_map<A: serde::de::MapAccess<'de>>(
                    self,
                    mut a: A,
                ) -> std::result::Result<Unique, A::Error> {
                    let mut values = serde_json::Map::new();
                    while let Some((key, Unique(value))) = a.next_entry::<String, Unique>()? {
                        if values.len() >= 4096 || values.insert(key, value).is_some() {
                            return Err(serde::de::Error::custom(
                                "duplicate or excessive configuration keys",
                            ));
                        }
                    }
                    Ok(Unique(Value::Object(values)))
                }
            }
            d.deserialize_any(V)
        }
    }
    require(
        !raw.is_empty() && raw.len() as u64 <= MAX_CONFIG,
        "bounded configuration body",
    )?;
    Ok(serde_json::from_slice::<Unique>(raw)?.0)
}
fn keys(v: &Value, required: &[&str], optional: &[&str]) -> Result<()> {
    let object = v.as_object().ok_or("configuration object required")?;
    require(
        required.iter().all(|k| object.contains_key(*k))
            && object
                .keys()
                .all(|k| required.contains(&k.as_str()) || optional.contains(&k.as_str())),
        "closed configuration keys",
    )
}
fn text<'a>(v: &'a Value, key: &str) -> Result<&'a str> {
    v.get(key)
        .and_then(Value::as_str)
        .ok_or_else(|| format!("string field {key} required").into())
}
fn identifier(name: &str) -> bool {
    !name.is_empty()
        && name.len() <= 128
        && name
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"_-".contains(&b))
}
fn table<'a>(v: &'a Value, key: &str) -> Result<&'a [Value]> {
    match v.get(key) {
        None => Ok(&[]),
        Some(a) => {
            let a = a.as_array().ok_or("configuration array required")?;
            require(a.len() <= 512, "bounded configuration table")?;
            Ok(a)
        }
    }
}
fn profile_document(raw: &[u8]) -> Result<Value> {
    let v = unique_json(raw)?;
    keys(&v, &[], &["Attributes", "Profiles", "AggregateProfiles"])?;
    for key in ["Attributes", "Profiles", "AggregateProfiles"] {
        let mut names = BTreeSet::new();
        for row in table(&v, key)? {
            let name = text(row, "Name")?;
            require(
                identifier(name) && names.insert(name.to_owned()),
                "unique per-layer profile/attribute name",
            )?;
            match key {
                "Attributes" => {
                    keys(row, &["Name", "Controller", "File"], &["FileV2"])?;
                    require(
                        ["cpu", "cpuset", "memory", "freezer", "cgroup2", "io"]
                            .contains(&text(row, "Controller")?),
                        "known native attribute controller",
                    )?;
                    for field in ["File", "FileV2"] {
                        if let Some(v) = row.get(field) {
                            let value = v.as_str().ok_or("attribute file string")?;
                            require(
                                !value.is_empty()
                                    && value.len() <= 160
                                    && !value.starts_with('/')
                                    && !value.contains("..")
                                    && value
                                        .bytes()
                                        .all(|b| b.is_ascii_alphanumeric() || b"._-/".contains(&b)),
                                "fixed relative attribute role",
                            )?;
                        }
                    }
                }
                "Profiles" => {
                    keys(row, &["Name", "Actions"], &[])?;
                    let actions = row["Actions"].as_array().ok_or("profile action array")?;
                    require(
                        !actions.is_empty() && actions.len() <= 64,
                        "nonempty bounded action sequence",
                    )?;
                    for action in actions {
                        validate_action(action)?;
                    }
                }
                _ => {
                    keys(row, &["Name", "Profiles"], &[])?;
                    let items = row["Profiles"]
                        .as_array()
                        .ok_or("aggregate profile array")?;
                    require(
                        !items.is_empty()
                            && items.len() <= 64
                            && items.iter().all(|v| v.as_str().is_some_and(identifier)),
                        "nonempty fixed aggregate sequence",
                    )?;
                }
            }
        }
    }
    Ok(v)
}
fn validate_action(action: &Value) -> Result<()> {
    keys(action, &["Name", "Params"], &[])?;
    let params = &action["Params"];
    match text(action, "Name")? {
        "JoinCgroup" => {
            keys(params, &["Controller", "Path"], &[])?;
            let controller = text(params, "Controller")?;
            let path = text(params, "Path")?;
            require(
                match controller {
                    "cpu" => CPU_CLASSES[1..].contains(&path),
                    "cpuset" => SET_CLASSES.contains(&path),
                    "blkio" => ["", "background"].contains(&path),
                    "memory" => path == "system",
                    _ => false,
                },
                "registered actual v2 join",
            )?;
        }
        "SetAttribute" => {
            keys(params, &["Name", "Value"], &["Optional"])?;
            require(
                identifier(text(params, "Name")?)
                    && !text(params, "Value")?.is_empty()
                    && text(params, "Value")?.len() <= 128,
                "fixed attribute name/value",
            )?;
            if let Some(v) = params.get("Optional") {
                require(
                    v.as_str().is_some_and(|s| s == "true" || s == "false"),
                    "literal optional field",
                )?;
            }
        }
        "SetTimerSlack" => {
            keys(params, &["Slack"], &[])?;
            let slack = text(params, "Slack")?.parse::<u64>()?;
            require(
                slack > 0 && slack <= i64::MAX as u64,
                "positive bounded timer slack without silent reset",
            )?;
        }
        "SetSchedulerPolicy" => {
            let policy = text(params, "Policy")?;
            if ["SCHED_OTHER", "SCHED_BATCH", "SCHED_IDLE"].contains(&policy) {
                keys(params, &["Policy"], &["Nice"])?;
                if params.get("Nice").is_some() {
                    require(
                        (-20..=19).contains(&text(params, "Nice")?.parse::<i32>()?),
                        "normal nice range",
                    )?;
                }
            } else {
                keys(params, &["Policy", "Priority"], &[])?;
                require(
                    ["SCHED_FIFO", "SCHED_RR"].contains(&policy)
                        && (1..=99).contains(&text(params, "Priority")?.parse::<u32>()?),
                    "fixed realtime virtual priority",
                )?;
            }
        }
        "Compact" => {
            keys(params, &["Type"], &[])?;
            require(
                ["full", "anon", "file"].contains(&text(params, "Type")?),
                "fixed memory compaction role",
            )?;
        }
        kind => return Err(format!("unsupported effective native action {kind}").into()),
    }
    Ok(())
}
fn original_library_metadata(
    inputs: &Inputs,
    runner: &mut Runner<'_>,
    plan: &BuildPlan,
    output: &Path,
    deadline: &Deadline,
    name: &str,
) -> Result<FileRef> {
    require(
        ["libprocessgroup.so", "libprocessgroup_setup.so"].contains(&name),
        "one of two fixed native libraries",
    )?;
    let label_path = output.join(format!("ORIGINAL-{name}-SELINUX.bin"));
    let source = format!("/system/lib64/{name}");
    absolute(&label_path)?;
    require(
        !label_path.try_exists()?,
        "create-only original library label capture",
    )?;
    debug(
        inputs,
        runner,
        plan,
        &plan.system,
        &format!(
            "ea_get -f \"{}\" {source} security.selinux",
            label_path.display()
        ),
    )?;
    require(
        std::fs::read(&label_path)? == b"u:object_r:system_lib_file:s0\0",
        "actual original library SELinux role",
    )?;
    let attrs = debug(
        inputs,
        runner,
        plan,
        &plan.system,
        &format!("ea_list {source}"),
    )?;
    let rows: Vec<_> = std::str::from_utf8(&attrs)?
        .lines()
        .filter(|s| !s.trim().is_empty())
        .collect();
    require(
        rows.len() == 2
            && rows[0] == "Extended attributes:"
            && rows[1].trim_start().starts_with("security.selinux ("),
        "complete original library xattr catalog without file capability",
    )?;
    io::actual_ref(&label_path, deadline)
}
// Mirror ReadDescriptors' actual layer order and replacement-by-name. Do not
// silently discard API/vendor descriptors just because the base is v2-only.
fn effective_cgroups(documents: &[Value]) -> Result<Value> {
    let mut descriptors = BTreeMap::<String, Value>::new();
    fn merge(
        out: &mut BTreeMap<String, Value>,
        row: &Value,
        name: &str,
        root: &str,
        version: u32,
    ) -> Result<()> {
        keys(
            row,
            &["Path"],
            &[
                "Controller",
                "Mode",
                "UID",
                "GID",
                "NeedsActivation",
                "Optional",
                "MaxActivationDepth",
                "Controllers",
            ],
        )?;
        require(identifier(name), "fixed descriptor name")?;
        let path = text(row, "Path")?;
        let path = if root.is_empty() {
            path.to_owned()
        } else if path == "." {
            root.to_owned()
        } else {
            format!("{root}/{path}")
        };
        require(
            path.starts_with('/')
                && !path.contains("//")
                && !path.contains("..")
                && !path.ends_with('/'),
            "canonical descriptor path",
        )?;
        for flag in ["NeedsActivation", "Optional"] {
            if let Some(v) = row.get(flag) {
                require(v.is_boolean(), "boolean descriptor flag")?;
            }
        }
        let mode = match row.get("Mode") {
            None => 0,
            Some(v) => {
                let s = v.as_str().ok_or("octal descriptor mode")?;
                require(
                    !s.is_empty() && s.len() <= 5 && s.bytes().all(|b| (b'0'..=b'7').contains(&b)),
                    "exact octal descriptor mode",
                )?;
                u32::from_str_radix(s, 8)?
            }
        };
        let uid = match row.get("UID") {
            None => "",
            Some(v) => v.as_str().ok_or("descriptor uid")?,
        };
        let gid = match row.get("GID") {
            None => "",
            Some(v) => v.as_str().ok_or("descriptor gid")?,
        };
        let depth = match row.get("MaxActivationDepth") {
            None => u32::MAX,
            Some(v) => u32::try_from(v.as_u64().ok_or("descriptor depth")?)?,
        };
        out.insert(name.to_owned(),json!({"version":version,"path":path,"mode":mode,"uid":uid,"gid":gid,
            "needs_activation":row.get("NeedsActivation").and_then(Value::as_bool).unwrap_or(false),
            "optional":row.get("Optional").and_then(Value::as_bool).unwrap_or(false),"max_activation_depth":depth}));
        Ok(())
    }
    for document in documents {
        keys(document, &[], &["Cgroups", "Cgroups2"])?;
        let mut seen = BTreeSet::new();
        for row in table(document, "Cgroups")? {
            let name = text(row, "Controller")?;
            require(seen.insert(name.to_owned()), "unique per-layer controller")?;
            merge(&mut descriptors, row, name, "", 1)?;
        }
        if let Some(root) = document.get("Cgroups2") {
            keys(
                root,
                &["Path", "Controllers"],
                &[
                    "Mode",
                    "UID",
                    "GID",
                    "NeedsActivation",
                    "Optional",
                    "MaxActivationDepth",
                ],
            )?;
            require(seen.insert("cgroup2".into()), "one cgroup2 root descriptor")?;
            merge(&mut descriptors, root, "cgroup2", "", 2)?;
            for row in table(root, "Controllers")? {
                let name = text(row, "Controller")?;
                require(seen.insert(name.to_owned()), "unique per-layer controller")?;
                merge(&mut descriptors, row, name, text(root, "Path")?, 2)?;
            }
        }
    }
    let expected_names = BTreeSet::from([
        "cgroup2", "cpu", "cpuset", "io", "memory", "pids", "freezer",
    ]);
    require(
        descriptors
            .keys()
            .map(String::as_str)
            .collect::<BTreeSet<_>>()
            == expected_names,
        "complete effective v2-only controller catalog",
    )?;
    for (name, row) in &descriptors {
        require(
            row["version"] == 2
                && row["path"] == "/sys/fs/cgroup"
                && row["optional"] == false
                && row["max_activation_depth"] == u32::MAX
                && row["needs_activation"] == !matches!(name.as_str(), "cgroup2" | "freezer"),
            "effective controller type/path/activation",
        )?;
        if name == "cgroup2" {
            require(
                row["mode"] == 0o775 && row["uid"] == "root" && row["gid"] == "system",
                "original delegated root ownership",
            )?;
        } else {
            require(
                row["mode"] == 0 && row["uid"] == "" && row["gid"] == "",
                "no unconsumed controller mount ownership override",
            )?;
        }
    }
    Ok(serde_json::to_value(descriptors)?)
}
#[derive(Clone)]
enum ProfileNode {
    Actions(Vec<Value>),
    Aggregate(Vec<usize>),
}

fn rc_disposition(original: &[u8], derived: &[u8]) -> Result<(Vec<String>, Vec<Value>)> {
    let roots = ["/dev/cpuctl", "/dev/cpuset", "/dev/blkio", "/dev/memcg"];
    let is_legacy = |word: &str| {
        roots
            .iter()
            .any(|root| word == *root || word.starts_with(&format!("{root}/")))
    };
    for line in std::str::from_utf8(derived)?.lines() {
        let command = line.split('#').next().unwrap_or("").trim();
        require(
            !command.split_ascii_whitespace().any(is_legacy),
            "derived init RC still attempts an unimplemented v1 cgroup operation",
        )?;
    }
    let mut unsupported = Vec::new();
    let mut records = Vec::new();
    for (index, line) in std::str::from_utf8(original)?.lines().enumerate() {
        let command = line.split('#').next().unwrap_or("").trim();
        let words: Vec<_> = command.split_ascii_whitespace().collect();
        if !words.iter().any(|word| is_legacy(word)) {
            continue;
        }
        require(
            matches!(
                words.first().copied(),
                Some("mkdir" | "chown" | "chmod" | "copy" | "write")
            ),
            "unregistered original cgroup RC operation",
        )?;
        let target = *words
            .iter()
            .find(|word| is_legacy(word))
            .ok_or("original cgroup path")?;
        let disposition = if words[0] == "write" {
            match (target, words.last().copied()) {
                ("/dev/cpuctl/nnapi-hal/cpu.uclamp.min", Some("1")) => {
                    "native_nnapi_class_min_1_only"
                }
                ("/dev/cpuctl/nnapi-hal/cpu.uclamp.latency_sensitive", Some("1")) => {
                    unsupported.push("nnapi_latency_sensitive_hint".into());
                    "unimplemented_no_replacement_floor"
                }
                ("/dev/blkio/blkio.weight", Some("1000"))
                | ("/dev/blkio/background/blkio.weight", Some("200")) => {
                    "explicit_v2_domain_io_weight_policy"
                }
                ("/dev/blkio/background/blkio.prio.class", Some("restrict-to-be")) => {
                    "native_domain_io_prio_class"
                }
                ("/dev/blkio/background/blkio.bfq.weight", Some("10"))
                | (
                    "/dev/blkio/blkio.group_idle" | "/dev/blkio/background/blkio.group_idle",
                    Some("0"),
                ) => "explicit_v2_io_policy_no_bfq_or_group_idle_equivalence",
                _ => {
                    return Err(
                        format!("unregistered original RC write at line {}", index + 1).into(),
                    );
                }
            }
        } else if target.ends_with("/memory.pressure_level") {
            unsupported.push("v1_memory_pressure_level_interface".into());
            "unimplemented_v1_pressure_interface"
        } else if target.starts_with("/dev/cpuctl") {
            "native_owned_cpu_classes_and_scoped_delegation"
        } else if target.starts_with("/dev/cpuset") {
            "native_dual_axis_classes_with_actual_selected_cpu_and_mems_masks"
        } else if target.starts_with("/dev/memcg") {
            "native_original_process_memory_domain"
        } else {
            "native_domain_io_and_per_task_io_context"
        };
        records.push(
            json!({"source_line":index+1,"original":line,"disposition":disposition,
            "actual_execution_qualified":false}),
        );
    }
    require(
        !records.is_empty() && records.len() <= 512,
        "complete bounded original RC cgroup inventory",
    )?;
    unsupported.sort();
    unsupported.dedup();
    Ok((unsupported, records))
}
fn effective_profiles(documents: &[Value]) -> Result<(Vec<String>, Value)> {
    let mut names = BTreeMap::<String, usize>::new();
    let mut nodes = Vec::<ProfileNode>::new();
    let mut attributes = BTreeMap::<String, Value>::new();
    for document in documents {
        for row in table(document, "Attributes")? {
            attributes.insert(text(row, "Name")?.into(), row.clone());
        }
        for row in table(document, "Profiles")? {
            let name = text(row, "Name")?;
            let actions = row["Actions"].as_array().ok_or("profile actions")?.clone();
            for action in &actions {
                if text(action, "Name")? == "SetAttribute" {
                    require(
                        attributes.contains_key(text(&action["Params"], "Name")?),
                        "native action attribute must already exist at that layer",
                    )?;
                }
            }
            // The native implementation mutates the existing TaskProfile;
            // aggregates holding it observe that replacement, not a snapshot.
            let node = ProfileNode::Actions(actions);
            if let Some(&id) = names.get(name) {
                nodes[id] = node;
            } else {
                names.insert(name.into(), nodes.len());
                nodes.push(node);
            }
        }
        for row in table(document, "AggregateProfiles")? {
            let name = text(row, "Name")?;
            let mut edges = Vec::new();
            for value in row["Profiles"].as_array().ok_or("aggregate sequence")? {
                let item = value.as_str().ok_or("aggregate item")?;
                require(item != name, "native direct aggregate recursion")?;
                edges.push(
                    *names
                        .get(item)
                        .ok_or("aggregate references a profile not yet defined")?,
                );
            }
            // Native aggregate replacement creates a new shared_ptr object.
            // Earlier aggregates retain the prior object; model that identity.
            names.insert(name.into(), nodes.len());
            nodes.push(ProfileNode::Aggregate(edges));
        }
        require(nodes.len() <= 4096, "bounded actual profile object graph")?;
    }
    fn flatten(
        id: usize,
        nodes: &[ProfileNode],
        active: &mut BTreeSet<usize>,
        out: &mut Vec<Value>,
    ) -> Result<()> {
        require(
            active.len() < 32 && active.insert(id),
            "bounded acyclic actual profile object graph",
        )?;
        match &nodes[id] {
            ProfileNode::Actions(actions) => {
                require(
                    out.len() + actions.len() <= 4096,
                    "bounded effective action sequence",
                )?;
                out.extend_from_slice(actions);
            }
            ProfileNode::Aggregate(edges) => {
                for &edge in edges {
                    flatten(edge, nodes, active, out)?;
                }
            }
        }
        active.remove(&id);
        Ok(())
    }
    let mut unsupported = Vec::new();
    let mut effective = BTreeMap::new();
    for (name, &id) in &names {
        let mut actions = Vec::new();
        flatten(id, &nodes, &mut BTreeSet::new(), &mut actions)?;
        for action in &actions {
            if text(action, "Name")? == "SetAttribute" {
                let attribute = attributes
                    .get(text(&action["Params"], "Name")?)
                    .ok_or("effective action references absent attribute")?;
                let file = attribute
                    .get("FileV2")
                    .unwrap_or(&attribute["File"])
                    .as_str()
                    .ok_or("effective attribute file")?;
                // Unsupported latency and v1-only interfaces remain explicit.
                if file == "cpu.uclamp.latency_sensitive"
                    || [
                        "memory.usage_in_bytes",
                        "memory.memsw.usage_in_bytes",
                        "memory.pressure_level",
                        "cgroup.event_control",
                    ]
                    .contains(&file)
                {
                    unsupported.push(name.clone());
                }
            }
        }
        effective.insert(name.clone(), actions);
    }
    unsupported.sort();
    unsupported.dedup();
    Ok((
        unsupported,
        json!({"attributes":attributes,"profiles":effective,"object_count":nodes.len(),"order_and_pointer_replacement_preserved":true}),
    ))
}

pub(crate) fn prepare(
    n: &NativeInput,
    plan: &BuildPlan,
    adapter: &Adapter,
    contents: &mut BTreeMap<String, Vec<u8>>,
    inputs: &mut Inputs,
    runner: &mut Runner<'_>,
    output: &Path,
    deadline: &Deadline,
    images: &BTreeMap<String, FileRef>,
) -> Result<NativeDeclaration> {
    require(
        n.schema == "droidloom-native-v2-input-v1" && (1..=10000).contains(&n.first_api_level),
        "native input schema/API bound",
    )?;
    for r in [
        &n.original_elf,
        &n.derived_elf,
        &n.original_setup_elf,
        &n.derived_setup_elf,
    ] {
        r.validate(MAX_ELF)?;
    }
    for r in [&n.build_provenance, &n.placement_provenance] {
        r.validate(MAX_PLAN)?;
    }
    let original = inputs.bytes(&n.original_elf, MAX_ELF, deadline)?;
    let derived = inputs.bytes(&n.derived_elf, MAX_ELF, deadline)?;
    require(
        crate::produce::original_cat(inputs, runner, plan, "/system/lib64/libprocessgroup.so")?
            == original,
        "selected original libprocessgroup bytes",
    )?;
    let original_label =
        original_library_metadata(inputs, runner, plan, output, deadline, "libprocessgroup.so")?;
    let original_setup = inputs.bytes(&n.original_setup_elf, MAX_ELF, deadline)?;
    let derived_setup = inputs.bytes(&n.derived_setup_elf, MAX_ELF, deadline)?;
    require(
        crate::produce::original_cat(
            inputs,
            runner,
            plan,
            "/system/lib64/libprocessgroup_setup.so",
        )? == original_setup,
        "selected original setup library bytes",
    )?;
    let original_setup_label = original_library_metadata(
        inputs,
        runner,
        plan,
        output,
        deadline,
        "libprocessgroup_setup.so",
    )?;
    let original_setup_elf = elf(&original_setup)?;
    let derived_setup_elf = elf(&derived_setup)?;
    require(
        original_setup_elf.soname == "libprocessgroup_setup.so"
            && derived_setup_elf.soname == original_setup_elf.soname
            && original_setup_elf.exports == derived_setup_elf.exports,
        "fixed setup DSO exported symbol/data surface",
    )?;
    let original_elf = elf(&original)?;
    let derived_elf = elf(&derived)?;
    require(
        original_elf.soname == "libprocessgroup.so"
            && derived_elf.soname == original_elf.soname
            && original_elf.exports == derived_elf.exports,
        "fixed DSO exported symbol/data surface",
    )?;
    let proof_raw = inputs.bytes(&n.build_provenance, MAX_PLAN, deadline)?;
    let proof: BuildProvenance = serde_json::from_slice(&proof_raw)?;
    require(
        proof.schema == "droidloom-native-v2-build-provenance-v2"
            && proof.source_basis == "public-reference-not-source-equivalent"
            && proof.source_system_sha256 == plan.system.sha256
            && proof.original_elf_sha256 == n.original_elf.sha256
            && proof.derived_elf_sha256 == n.derived_elf.sha256
            && proof.original_setup_elf_sha256 == n.original_setup_elf.sha256
            && proof.derived_setup_elf_sha256 == n.derived_setup_elf.sha256,
        "actual build provenance binds both original/derived DSO pairs and this system",
    )?;
    let source_manifest = inputs.bytes(&proof.source_manifest, MAX_PLAN, deadline)?;
    let toolchain_manifest = inputs.bytes(&proof.toolchain_manifest, MAX_PLAN, deadline)?;
    let build_raw = inputs.bytes(&proof.actual_build_result, 96 * 1024, deadline)?;
    let retirement_raw = inputs.bytes(&proof.actual_retirement, 96 * 1024, deadline)?;
    let abi_raw = inputs.bytes(&proof.actual_abi_result, 96 * 1024, deadline)?;
    let abi_tables = inputs.bytes(&proof.actual_abi_tables, 16 * 1024 * 1024, deadline)?;
    let pair = |raw: &[u8], parsed: &Elf| build_evidence::Artifact {
        file: build_evidence::Pin::of(raw),
        build_id: parsed.build_id.clone(),
    };
    let pairs = build_evidence::Pairs {
        original_main: pair(&original, &original_elf),
        derived_main: pair(&derived, &derived_elf),
        original_setup: pair(&original_setup, &original_setup_elf),
        derived_setup: pair(&derived_setup, &derived_setup_elf),
    };
    let build_evidence = build_evidence::Receipt {
        schema: "droidloom-native-build-receipt-v1".into(),
        source_manifest: build_evidence::Pin::of(&source_manifest),
        toolchain_manifest: build_evidence::Pin::of(&toolchain_manifest),
        build_result: build_evidence::RawReport::new(&build_raw)?,
        abi_result: build_evidence::RawReport::new(&abi_raw)?,
        retirement: build_evidence::RawReport::new(&retirement_raw)?,
    };
    build_evidence.validate(&build_evidence::Bindings {
        source_system_sha256: &plan.system.sha256,
        source_basis: &proof.source_basis,
        pairs: &pairs,
    })?;
    build_evidence.validate_inputs(&source_manifest, &toolchain_manifest)?;
    build_evidence.validate_surface_counts([
        original_elf.exports.len() as u64,
        derived_elf.exports.len() as u64,
        original_setup_elf.exports.len() as u64,
        derived_setup_elf.exports.len() as u64,
    ])?;
    build_evidence.validate_tables_pin(&abi_tables)?;
    let placement = inputs.bytes(&n.placement_provenance, MAX_PLAN, deadline)?;
    let placement_value = unique_json(&placement)?;
    keys(
        &placement_value,
        &[
            "schema",
            "normal_cpus",
            "little_cpus",
            "graphics_cpus",
            "mems",
            "root_cpus",
            "actual_topology",
        ],
        &[],
    )?;
    require(
        placement_value["schema"] == "droidloom-native-placement-input-v1"
            && placement_value["normal_cpus"] == n.normal_cpus
            && placement_value["little_cpus"] == n.little_cpus
            && placement_value["graphics_cpus"] == n.graphics_cpus
            && placement_value["mems"] == n.mems
            && placement_value["root_cpus"] == "2-23",
        "placement evidence binds the requested masks",
    )?;
    let topology: FileRef = serde_json::from_value(placement_value["actual_topology"].clone())?;
    let topology_raw = inputs.bytes(&topology, MAX_PLAN, deadline)?;
    require(
        unique_json(&topology_raw)?.is_object(),
        "whole original topology observation",
    )?;
    let root = mask("2-23")?;
    for m in [&n.normal_cpus, &n.little_cpus, &n.graphics_cpus] {
        require(
            mask(m)?.is_subset(&root),
            "placement stays within original hard CPU budget",
        )?;
    }
    mask(&n.mems)?;
    let mut dependencies = BTreeMap::new();
    require(
        !n.dependencies.is_empty() && n.dependencies.len() <= 128,
        "bounded actual dependency closure",
    )?;
    for dep in &n.dependencies {
        dep.elf.validate(MAX_ELF)?;
        absolute(Path::new(&dep.image_path))?;
        absolute(Path::new(&dep.guest_path))?;
        let image = images
            .get(&dep.image_role)
            .ok_or("dependency source is not an admitted original image/APEX payload")?;
        let expected = if dep.image_role == "system" {
            dep.image_path.clone()
        } else if dep.image_role == "vendor" {
            format!("/vendor{}", dep.image_path)
        } else {
            format!(
                "/apex/{}{}",
                dep.image_role
                    .strip_prefix("apex:")
                    .ok_or("fixed image role")?,
                dep.image_path
            )
        };
        require(
            expected == dep.guest_path && !dep.guest_path.contains("/../"),
            "fixed selected library source mapping",
        )?;
        let body = inputs.bytes(&dep.elf, MAX_ELF, deadline)?;
        require(
            image_optional(inputs, runner, plan, image, &dep.image_path)?.as_ref() == Some(&body),
            "actual dependency bytes from selected image",
        )?;
        let parsed = elf(&body)?;
        require(
            dependency_location(
                &dep.image_role,
                &dep.image_path,
                &dep.guest_path,
                &parsed.soname,
            ),
            "fixed dependency path/soname role",
        )?;
        require(
            dependencies
                .insert(parsed.soname.clone(), (dep, parsed))
                .is_none(),
            "unique actual dependency soname",
        )?;
    }
    require(
        !dependencies.contains_key("libprocessgroup.so")
            && !dependencies.contains_key("libprocessgroup_setup.so"),
        "derived roles cannot be shadowed by dependency inputs",
    )?;
    let fixed_dependencies: BTreeSet<_> = [
        "libbase.so",
        "libjsoncpp.so",
        "libcrypto.so",
        "libc++.so",
        "liblog.so",
        "libc.so",
        "libm.so",
        "libdl.so",
        "ld-android.so",
    ]
    .into_iter()
    .map(str::to_owned)
    .collect();
    require(
        dependencies.keys().cloned().collect::<BTreeSet<_>>() == fixed_dependencies,
        "exact accepted nine-dependency, two-derived-library closure",
    )?;
    let mut symbols: BTreeSet<_> = derived_elf
        .exports
        .keys()
        .cloned()
        .chain(derived_setup_elf.exports.keys().cloned())
        .collect();
    for (_, e) in dependencies.values() {
        symbols.extend(e.exports.keys().cloned());
    }
    for e in [&derived_elf, &derived_setup_elf]
        .into_iter()
        .chain(dependencies.values().map(|(_, e)| e))
    {
        require(
            e.needed.iter().all(|name| {
                dependencies.contains_key(name)
                    || name == "libprocessgroup.so"
                    || name == "libprocessgroup_setup.so"
            }) && e.required_imports.is_subset(&symbols),
            "complete concrete needed-library/import closure",
        )?;
    }
    let mut actual_tables = vec![
        json!({"role":"original_main","file":build_evidence::Pin::of(&original),"elf":original_elf}),
        json!({"role":"derived_main","file":build_evidence::Pin::of(&derived),"elf":derived_elf}),
        json!({"role":"original_setup","file":build_evidence::Pin::of(&original_setup),"elf":original_setup_elf}),
        json!({"role":"derived_setup","file":build_evidence::Pin::of(&derived_setup),"elf":derived_setup_elf}),
    ];
    for (name, (dep, parsed)) in &dependencies {
        actual_tables.push(json!({"role":format!("dependency:{name}"),
        "file":{"bytes":dep.elf.bytes,"sha256":dep.elf.sha256},"elf":parsed}));
    }
    require(
        unique_json(&abi_tables)?
            == json!({"schema":"droidloom-native-elf-table-catalog-v1","entries":actual_tables}),
        "complete recorded ABI tables equal independently parsed actual thirteen original/derived/dependency ELF bodies",
    )?;
    let mut records = Vec::new();
    records.push(json!({"path":"/system/lib64/libprocessgroup.so","bytes":derived.len(),"sha256":io::hash(&derived),"absent":false}));
    for (name, path) in [
        ("cgroups.json", "/system/etc/cgroups.json"),
        ("task_profiles.json", "/etc/task_profiles.json"),
    ] {
        let body = contents
            .get(name)
            .ok_or("derived effective base configuration")?;
        records
            .push(json!({"path":path,"bytes":body.len(),"sha256":io::hash(body),"absent":false}));
    }
    let mut cgroup_documents = vec![unique_json(
        contents.get("cgroups.json").ok_or("effective cgroups")?,
    )?];
    let base = profile_document(contents.get("task_profiles.json").ok_or("base profiles")?)?;
    let mut documents = vec![base];
    let optional = [
        (
            "system",
            format!(
                "/system/etc/task_profiles/task_profiles_{}.json",
                n.first_api_level
            ),
            format!(
                "/etc/task_profiles/task_profiles_{}.json",
                n.first_api_level
            ),
        ),
        (
            "vendor",
            "/etc/task_profiles.json".into(),
            "/vendor/etc/task_profiles.json".into(),
        ),
        (
            "system",
            "/system/system_ext/etc/task_profiles.json".into(),
            "/system_ext/etc/task_profiles.json".into(),
        ),
    ];
    for (role, source, guest) in optional {
        let body = image_optional(
            inputs,
            runner,
            plan,
            images.get(role).ok_or("fixed source image")?,
            &source,
        )?;
        if let Some(raw) = &body {
            require(raw.len() as u64 <= MAX_CONFIG, "bounded actual override")?;
            documents.push(profile_document(raw)?);
        }
        records.push(json!({"path":guest,"bytes":body.as_ref().map_or(0,Vec::len),"sha256":body.as_ref().map_or(String::new(),|b|io::hash(b)),"absent":body.is_none()}));
    }
    records.push(json!({"path":"/system/lib64/libprocessgroup_setup.so","bytes":derived_setup.len(),"sha256":io::hash(&derived_setup),"absent":false}));
    for (role, source, guest) in [
        (
            "system",
            format!(
                "/system/etc/task_profiles/cgroups_{}.json",
                n.first_api_level
            ),
            format!("/etc/task_profiles/cgroups_{}.json", n.first_api_level),
        ),
        (
            "vendor",
            "/etc/cgroups.json".into(),
            "/vendor/etc/cgroups.json".into(),
        ),
    ] {
        let body = image_optional(
            inputs,
            runner,
            plan,
            images.get(role).ok_or("fixed controller source image")?,
            &source,
        )?;
        if let Some(raw) = &body {
            cgroup_documents.push(unique_json(raw)?);
        }
        records.push(json!({"path":guest,"bytes":body.as_ref().map_or(0,Vec::len),"sha256":body.as_ref().map_or(String::new(),|b|io::hash(b)),"absent":body.is_none()}));
    }
    require(
        records.len() == 9,
        "complete two-DSO and ordered profile/controller input catalog",
    )?;
    let cgroups = effective_cgroups(&cgroup_documents)?;
    let (unsupported, effective_profile_graph) = effective_profiles(&documents)?;
    let original_rc =
        crate::produce::original_cat(inputs, runner, plan, "/system/etc/init/hw/init.rc")?;
    let (unsupported_rc_actions, rc_actions) = rc_disposition(
        &original_rc,
        contents.get("init.rc").ok_or("derived init RC")?,
    )?;
    let cpus: Vec<_> = SET_ROLES
        .iter()
        .map(|role| match *role {
            "little" => &n.little_cpus,
            "graphics" => &n.graphics_cpus,
            _ => &n.normal_cpus,
        })
        .collect();
    let policy = json!({"schema":1,"backend":"droidloom-native-v2","cpu_weights":WEIGHTS,"cpuset_cpus":cpus,
        "cpuset_mems":n.mems,"root_cpus":"2-23","inputs":records,"first_api_level":n.first_api_level,
        "uclamp_latency_sensitive":"reject-unimplemented"});
    let mut policy_raw = serde_json::to_vec_pretty(&policy)?;
    policy_raw.push(b'\n');
    require(
        policy_raw.len() as u64 <= MAX_CONFIG,
        "bounded fixed native policy",
    )?;
    // Native libraries retain the original library role, never a generic ELF
    // entrypoint. The derived file is new; no original inode is relabeled.
    for path in [
        "/lib64/libprocessgroup.so",
        "/lib64/libprocessgroup_setup.so",
    ] {
        require(
            adapter.selinux_contexts.get(path).map(String::as_str)
                == Some("u:object_r:system_lib_file:s0"),
            "fixed native library label",
        )?;
    }
    contents.insert("libprocessgroup.so".into(), derived.clone());
    contents.insert("libprocessgroup_setup.so".into(), derived_setup.clone());
    contents.insert("cgroup-v2-policy.json".into(), policy_raw.clone());
    let effective = io::json_new(
        &output.join("NATIVE-EFFECTIVE-INPUTS.json"),
        &json!({
        "schema":"droidloom-native-effective-inputs-v1","source_images":images,"ordered_inputs":records,
        "ordered_profile_documents":documents,"effective_profiles":effective_profile_graph,
        "ordered_controller_documents":cgroup_documents,"effective_cgroups":cgroups,
        "original_library_label":original_label,"original_setup_library_label":original_setup_label,
        "unsupported_effective_profiles":unsupported,
        "original_init_rc_sha256":io::hash(&original_rc),"original_rc_action_dispositions":rc_actions,
        "unsupported_rc_actions":unsupported_rc_actions,
        "placement_provenance":n.placement_provenance,"native_execution_qualified":false}),
        deadline,
    )?;
    let surface = io::json_new(
        &output.join("NATIVE-ELF-SURFACE.json"),
        &json!({
        "schema":"droidloom-native-elf-surface-v1","original":original_elf,"derived":derived_elf,
        "original_setup":original_setup_elf,"derived_setup":derived_setup_elf,
        "dependencies":dependencies.iter().map(|(name,(input,elf))|json!({"soname":name,"input":input.elf,"guest_path":input.guest_path,"elf":elf})).collect::<Vec<_>>(),
        "export_surface_equal":true,"version_sections_are_observations_not_equivalence":true,
        "cpp_abi_or_source_equivalence_proved":false,"native_execution_qualified":false}),
        deadline,
    )?;
    Ok(NativeDeclaration {
        scope: "droidloom-native-cgroup-v2-inputs-v2",
        source_system_sha256: plan.system.sha256.clone(),
        original_elf_sha256: n.original_elf.sha256.clone(),
        original_elf_bytes: original.len() as u64,
        original_build_id: original_elf.build_id,
        derived_build_id: derived_elf.build_id,
        library: ImageDeclaration {
            file: "lib64/libprocessgroup.so".into(),
            bytes: derived.len() as u64,
            sha256: io::hash(&derived),
        },
        original_setup_elf_sha256: n.original_setup_elf.sha256.clone(),
        original_setup_elf_bytes: original_setup.len() as u64,
        original_setup_build_id: original_setup_elf.build_id,
        derived_setup_build_id: derived_setup_elf.build_id,
        setup_library: ImageDeclaration {
            file: "lib64/libprocessgroup_setup.so".into(),
            bytes: derived_setup.len() as u64,
            sha256: io::hash(&derived_setup),
        },
        policy: ImageDeclaration {
            file: "rc/cgroup-v2-policy.json".into(),
            bytes: policy_raw.len() as u64,
            sha256: io::hash(&policy_raw),
        },
        source_provenance_sha256: n.build_provenance.sha256.clone(),
        effective_inputs_sha256: effective.sha256,
        abi_surface_sha256: surface.sha256,
        source_basis: proof.source_basis,
        native_execution_qualified: false,
        build_evidence,
        unsupported_effective_profiles: unsupported,
        unsupported_rc_actions,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    fn doc(v: Value) -> Value {
        profile_document(&serde_json::to_vec(&v).unwrap()).unwrap()
    }
    fn join(name: &str, path: &str) -> Value {
        json!({"Name":name,"Actions":[{"Name":"JoinCgroup","Params":{"Controller":"cpu","Path":path}}]})
    }
    #[test]
    fn native_dependency_accepts_only_fixed_runtime_loader_alias() {
        assert!(dependency_location(
            "apex:com.android.runtime",
            "/bin/linker64",
            "/apex/com.android.runtime/bin/linker64",
            "ld-android.so"
        ));
        assert!(dependency_location(
            "system",
            "/system/lib64/libbase.so",
            "/system/lib64/libbase.so",
            "libbase.so"
        ));
        for (role, source, guest, soname) in [
            (
                "system",
                "/bin/linker64",
                "/apex/com.android.runtime/bin/linker64",
                "ld-android.so",
            ),
            (
                "apex:other",
                "/bin/linker64",
                "/apex/com.android.runtime/bin/linker64",
                "ld-android.so",
            ),
            (
                "apex:com.android.runtime",
                "/bin/other",
                "/apex/com.android.runtime/bin/linker64",
                "ld-android.so",
            ),
            (
                "apex:com.android.runtime",
                "/bin/linker64",
                "/apex/com.android.runtime/bin/other",
                "ld-android.so",
            ),
            (
                "apex:com.android.runtime",
                "/bin/linker64",
                "/apex/com.android.runtime/bin/linker64",
                "linker64.so",
            ),
            (
                "system",
                "/system/lib64/libbase.so",
                "/system/lib64/libbase.so",
                "libother.so",
            ),
        ] {
            assert!(!dependency_location(role, source, guest, soname));
        }
    }
    fn base_controllers() -> Value {
        json!({"Cgroups":[],"Cgroups2":{"Path":"/sys/fs/cgroup","Mode":"0775","UID":"root","GID":"system","Controllers":[
            {"Controller":"cpu","Path":".","NeedsActivation":true},
            {"Controller":"cpuset","Path":".","NeedsActivation":true},
            {"Controller":"io","Path":".","NeedsActivation":true},
            {"Controller":"memory","Path":".","NeedsActivation":true},
            {"Controller":"pids","Path":".","NeedsActivation":true},
            {"Controller":"freezer","Path":"."}
        ]}})
    }
    #[test]
    fn native_configuration_rejects_duplicate_keys_and_unknown_actions() {
        assert!(profile_document(br#"{"Profiles":[],"Profiles":[]}"#).is_err());
        assert!(profile_document(br#"{"Profiles":[{"Name":"x","Actions":[{"Name":"JoinCgroup","Params":{"Controller":"cpu","Path":"background","Path":"top-app"}}]}]}"#).is_err());
        let unknown = json!({"Profiles":[{"Name":"arbitrary","Actions":[{"Name":"WriteFile","Params":{"FilePath":"/x","Value":"1"}}]}]});
        assert!(profile_document(&serde_json::to_vec(&unknown).unwrap()).is_err());
        assert!(profile_document(br#"{"Profiles":[{"Name":"Empty","Actions":[]}]}"#).is_err());
        assert!(profile_document(br#"{"Profiles":[{"Name":"Slack","Actions":[{"Name":"SetTimerSlack","Params":{"Slack":"0"}}]}]}"#).is_err());
    }
    #[test]
    fn native_profile_overrides_preserve_prior_aggregate_object_references() {
        let first = doc(
            json!({"Profiles":[join("A","background")],"AggregateProfiles":[
            {"Name":"B","Profiles":["A"]},{"Name":"C","Profiles":["B"]}]}),
        );
        let second = doc(
            json!({"Profiles":[join("A","top-app"),join("D","foreground")],
            "AggregateProfiles":[{"Name":"B","Profiles":["D"]}]}),
        );
        let (unsupported, effective) = effective_profiles(&[first, second]).unwrap();
        assert!(unsupported.is_empty());
        assert_eq!(effective["profiles"]["C"][0]["Params"]["Path"], "top-app");
        assert_eq!(
            effective["profiles"]["B"][0]["Params"]["Path"],
            "foreground"
        );
        let forward = doc(json!({"AggregateProfiles":[{"Name":"Before","Profiles":["Later"]}]}));
        let later = doc(json!({"Profiles":[join("Later","foreground")]}));
        assert!(effective_profiles(&[forward, later]).is_err());
    }
    #[test]
    fn native_controller_overrides_cannot_remove_io_or_restore_v1() {
        let base = base_controllers();
        assert!(effective_cgroups(&[base.clone()]).is_ok());
        let downgrade = json!({"Cgroups":[{"Controller":"io","Path":"/dev/blkio"}]});
        assert!(effective_cgroups(&[base.clone(), downgrade]).is_err());
        let disabled = json!({"Cgroups2":{"Path":"/sys/fs/cgroup","Mode":"0775","UID":"root","GID":"system","Controllers":[{"Controller":"io","Path":"."}]}});
        assert!(effective_cgroups(&[base.clone(), disabled]).is_err());
        let foreign = json!({"Cgroups2":{"Path":"/sys/fs/cgroup","Mode":"0775","UID":"root","GID":"system","Controllers":[{"Controller":"io","Path":"other","NeedsActivation":true}]}});
        assert!(effective_cgroups(&[base, foreign]).is_err());
    }
    #[test]
    fn native_effective_latency_is_reported_through_aggregate_without_a_clamp_floor() {
        let value = doc(
            json!({"Attributes":[{"Name":"Latency","Controller":"cpu","File":"cpu.uclamp.latency_sensitive"}],
            "Profiles":[{"Name":"Hint","Actions":[{"Name":"SetAttribute","Params":{"Name":"Latency","Value":"1"}}]}],
            "AggregateProfiles":[{"Name":"Caller","Profiles":["Hint"]}]}),
        );
        let (unsupported, effective) = effective_profiles(&[value]).unwrap();
        assert_eq!(unsupported, vec!["Caller", "Hint"]);
        assert_eq!(
            effective["profiles"]["Caller"][0]["Params"]["Name"],
            "Latency"
        );
        assert!(mask("02-3").is_err());
        assert!(mask("2,3").is_err());
        assert!(mask("2-3,3-4").is_err());
        assert_eq!(mask("2-23").unwrap().len(), 22);
    }
    #[test]
    fn native_rc_disposition_keeps_nnapi_min_separate_and_rejects_unhandled_commands() {
        let original=b"on init\n    write /dev/cpuctl/nnapi-hal/cpu.uclamp.min 1\n    write /dev/cpuctl/nnapi-hal/cpu.uclamp.latency_sensitive 1\n    chown root system /dev/memcg/memory.pressure_level\n";
        let derived = b"on init\n    # Native cgroup setup performs the selected operations.\n";
        let (unimplemented, rows) = rc_disposition(original, derived).unwrap();
        assert_eq!(
            unimplemented,
            vec![
                "nnapi_latency_sensitive_hint",
                "v1_memory_pressure_level_interface"
            ]
        );
        assert_eq!(rows[0]["disposition"], "native_nnapi_class_min_1_only");
        assert_eq!(rows[1]["disposition"], "unimplemented_no_replacement_floor");
        assert!(rc_disposition(original, original).is_err());
        assert!(
            rc_disposition(b"write /dev/cpuctl/nnapi-hal/cpu.uclamp.min 2\n", derived).is_err()
        );
    }
}
