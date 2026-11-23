//! Shared, strict data validation for an actually completed native build.
//! This is an offline build/symbol witness. It never authorizes execution.
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;

type Result<T> = std::result::Result<T, &'static str>;
fn need(value: bool, reason: &'static str) -> Result<()> {
    if value { Ok(()) } else { Err(reason) }
}
fn hex(value: &str, size: usize) -> bool {
    value.len() == size
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
fn digest(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct Pin {
    pub bytes: u64,
    pub sha256: String,
}
impl Pin {
    pub(crate) fn of(raw: &[u8]) -> Self {
        Self {
            bytes: raw.len() as u64,
            sha256: digest(raw),
        }
    }
    fn valid(&self, empty: bool) -> bool {
        hex(&self.sha256, 64)
            && (empty || self.bytes > 0)
            && (self.bytes != 0 || self.sha256 == digest(b""))
    }
}
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct Artifact {
    pub file: Pin,
    pub build_id: String,
}
impl Artifact {
    fn valid(&self) -> bool {
        self.file.valid(false)
            && self.file.bytes <= 4 * 1024 * 1024
            && (32..=128).contains(&self.build_id.len())
            && self.build_id.len() % 2 == 0
            && hex(&self.build_id, self.build_id.len())
    }
}
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct Pairs {
    pub original_main: Artifact,
    pub derived_main: Artifact,
    pub original_setup: Artifact,
    pub derived_setup: Artifact,
}
impl Pairs {
    fn valid(&self) -> bool {
        [
            &self.original_main,
            &self.derived_main,
            &self.original_setup,
            &self.derived_setup,
        ]
        .iter()
        .all(|a| a.valid())
            && self.original_main.file != self.derived_main.file
            && self.original_setup.file != self.derived_setup.file
    }
}
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Owner {
    boot_id: String,
    pid: u32,
    start: u64,
    invocation: String,
    unit: String,
}
impl Owner {
    fn valid(&self) -> bool {
        self.pid > 1
            && self.start > 0
            && hex(&self.invocation, 32)
            && self.boot_id.len() == 36
            && [8, 13, 18, 23]
                .iter()
                .all(|&i| self.boot_id.as_bytes()[i] == b'-')
            && hex(&self.boot_id.replace('-', ""), 32)
            && self.unit.starts_with("p4-native-v2-build-")
            && self.unit.ends_with(".service")
            && self.unit.len() <= 128
            && self
                .unit
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b))
    }
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct InputFile {
    path: String,
    file: Pin,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Origin {
    project: String,
    commit: String,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Manifest {
    schema: String,
    kind: String,
    files: Vec<InputFile>,
    origins: Vec<Origin>,
    bookended_unchanged: bool,
}
fn manifest(raw: &[u8], kind: &str) -> Result<Manifest> {
    let m: Manifest = serde_json::from_slice(raw).map_err(|_| "typed native input manifest")?;
    need(
        m.schema == "droidloom-native-build-input-manifest-v1"
            && m.kind == kind
            && m.bookended_unchanged
            && !m.files.is_empty()
            && m.files.len() <= 10000
            && !m.origins.is_empty()
            && m.origins.len() <= 32,
        "nonempty observed native input manifest",
    )?;
    let mut paths = BTreeSet::new();
    for f in &m.files {
        need(
            f.file.valid(true)
                && !f.path.is_empty()
                && f.path.len() <= 1024
                && !f.path.starts_with('/')
                && f.path
                    .split('/')
                    .all(|s| !s.is_empty() && s != "." && s != "..")
                && f.path.bytes().all(|b| b.is_ascii_graphic())
                && paths.insert(f.path.clone()),
            "unique bounded native input file",
        )?;
    }
    let mut projects = BTreeSet::new();
    for o in &m.origins {
        need(
            hex(&o.commit, 40) && !o.project.is_empty() && projects.insert(o.project.clone()),
            "unique pinned source origin",
        )?;
    }
    if kind == "source" {
        need(
            m.files.iter().any(|f| {
                f.path == "system/core/libprocessgroup/droidloom_v2.cpp" && f.file.valid(false)
            }) && m.origins.iter().any(|o| {
                o.project == "system/core" && o.commit == "545d2487e38192a2ce25040897ced877cf6b4f53"
            }),
            "fixed reviewed reference core and actual derived backend source",
        )?;
    } else {
        need(
            kind == "toolchain"
                && m.origins.iter().any(|o| {
                    o.project == "prebuilts/clang/host/linux-x86"
                        && o.commit == "29182889399818f97baa65ea238c80e8117981eb"
                }),
            "fixed official compiler source",
        )?;
        for role in [
            "clang-r584948/bin/clang-22",
            "clang-r584948/bin/lld",
            "clang-r584948/bin/llvm-ar",
            "clang-r584948/android_libc++/platform/x86_64/include/c++/v1/__config_site",
        ] {
            need(
                paths.contains(role),
                "complete fixed compiler and platform configuration roles",
            )?;
        }
        need(
            m.files.iter().any(|f| {
                f.path
                    .ends_with("/platform/x86_64/include/c++/v1/__config_site")
                    && f.file.bytes == 1802
                    && f.file.sha256
                        == "6a0ae8a59c944241e5dce284bb0f42f91f4cff48cb07f1b752a35e2fec9cfc08"
            }),
            "actual platform configuration, not the common host alias",
        )?;
    }
    Ok(m)
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct RawReport {
    pin: Pin,
    json: String,
}
impl RawReport {
    pub(crate) fn new(raw: &[u8]) -> Result<Self> {
        need(
            !raw.is_empty() && raw.len() <= 96 * 1024,
            "bounded complete native report",
        )?;
        Ok(Self {
            pin: Pin::of(raw),
            json: std::str::from_utf8(raw)
                .map_err(|_| "native report UTF-8")?
                .to_owned(),
        })
    }
    fn parse<T: serde::de::DeserializeOwned>(&self) -> Result<T> {
        need(
            !self.json.is_empty()
                && self.json.len() <= 96 * 1024
                && self.pin == Pin::of(self.json.as_bytes()),
            "complete native report bytes, not an unbound parsed claim",
        )?;
        serde_json::from_str(&self.json).map_err(|_| "strict native build report schema")
    }
}
#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
enum CommandRole {
    CompileCxx,
    CompileCrt,
    Archive,
    LinkMain,
    LinkSetup,
    Inspect,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Wait {
    pid: u32,
    code: i32,
    status: i32,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Command {
    sequence: u32,
    role: CommandRole,
    program: Pin,
    argv_sha256: String,
    pid: u32,
    start: u64,
    waitid: Wait,
    pidfd_reaped: bool,
    stdout: Pin,
    stderr: Pin,
    duration_ns: u64,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct BuildResult {
    schema: String,
    passed: bool,
    owner: Owner,
    source_manifest: Pin,
    toolchain_manifest: Pin,
    source_system_sha256: String,
    source_basis: String,
    pairs: Pairs,
    commands: Vec<Command>,
    original_inputs_unchanged: bool,
    absolute_deadline_met: bool,
    native_execution_qualified: bool,
    source_equivalence_proved: bool,
    android_starts: u32,
    host_policy_loads: u32,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct AbiResult {
    schema: String,
    passed: bool,
    pairs: Pairs,
    source_manifest: Pin,
    toolchain_manifest: Pin,
    scope: String,
    checker_source: Pin,
    complete_tables: Pin,
    library_count: u32,
    original_main_exports: u64,
    derived_main_exports: u64,
    original_setup_exports: u64,
    derived_setup_exports: u64,
    differing_defined_symbols: u64,
    unresolved_versioned_imports: u64,
    missing_needed_libraries: u64,
    unsupported_relocations: u64,
    executable_stack_or_wx_segments: u64,
    cpp_layout_or_source_equivalence: bool,
    native_execution_qualified: bool,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Retirement {
    schema: String,
    passed: bool,
    build_result: Pin,
    abi_result: Pin,
    source_manifest: Pin,
    toolchain_manifest: Pin,
    build_owner: Owner,
    observer: Owner,
    original_build_generation_absent: bool,
    original_cgroup_absent: bool,
    all_command_generations_absent: bool,
    original_inputs_unchanged: bool,
    absolute_deadline_met: bool,
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Receipt {
    pub schema: String,
    pub source_manifest: Pin,
    pub toolchain_manifest: Pin,
    pub build_result: RawReport,
    pub abi_result: RawReport,
    pub retirement: RawReport,
}
pub(crate) struct Bindings<'a> {
    pub source_system_sha256: &'a str,
    pub source_basis: &'a str,
    pub pairs: &'a Pairs,
}
/// Private construction follows validation of actual report bodies and pairs.
/// This type does not witness C++ object layout, native execution, or Ready.
#[derive(Debug)]
pub(crate) struct ValidatedBuild {
    _private: (),
}
impl Receipt {
    pub(crate) fn validate(&self, expected: &Bindings<'_>) -> Result<ValidatedBuild> {
        need(
            self.schema == "droidloom-native-build-receipt-v1"
                && self.source_manifest.valid(false)
                && self.toolchain_manifest.valid(false)
                && expected.pairs.valid()
                && hex(expected.source_system_sha256, 64)
                && expected.source_basis == "public-reference-not-source-equivalent",
            "fixed native build input receipt and honest source basis",
        )?;
        need(
            self.build_result.json.len() + self.abi_result.json.len() + self.retirement.json.len()
                <= 160 * 1024,
            "bounded embedded reports within the sealed runtime manifest",
        )?;
        let b: BuildResult = self.build_result.parse()?;
        let a: AbiResult = self.abi_result.parse()?;
        let r: Retirement = self.retirement.parse()?;
        need(
            b.schema == "droidloom-native-two-dso-build-result-v1"
                && b.passed
                && b.owner.valid()
                && b.source_manifest == self.source_manifest
                && b.toolchain_manifest == self.toolchain_manifest
                && b.source_system_sha256 == expected.source_system_sha256
                && b.source_basis == expected.source_basis
                && &b.pairs == expected.pairs
                && b.original_inputs_unchanged
                && b.absolute_deadline_met
                && !b.native_execution_qualified
                && !b.source_equivalence_proved
                && b.android_starts == 0
                && b.host_policy_loads == 0,
            "actual successful two-DSO build, exact inputs and four artifact bindings",
        )?;
        need(
            (6..=96).contains(&b.commands.len()),
            "complete finite actual command ledger",
        )?;
        let mut generations = BTreeSet::new();
        for (i, c) in b.commands.iter().enumerate() {
            need(
                c.sequence as usize == i
                    && c.program.valid(false)
                    && hex(&c.argv_sha256, 64)
                    && c.pid > 1
                    && c.pid != b.owner.pid
                    && c.start > 0
                    && c.waitid.pid == c.pid
                    && c.waitid.code == 1
                    && c.waitid.status == 0
                    && c.pidfd_reaped
                    && c.stdout.valid(true)
                    && c.stderr.valid(true)
                    && c.duration_ns > 0
                    && generations.insert((c.pid, c.start)),
                "real successful original child exit and bounded command identity",
            )?;
        }
        let count = |role| b.commands.iter().filter(|c| c.role == role).count();
        need(
            count(CommandRole::CompileCxx) > 0
                && count(CommandRole::CompileCrt) == 2
                && count(CommandRole::Archive) > 0
                && count(CommandRole::LinkMain) == 1
                && count(CommandRole::LinkSetup) == 1
                && count(CommandRole::Inspect) > 0,
            "actual compilation, real CRT, both links and static inspection occurred",
        )?;
        need(
            a.schema == "droidloom-native-two-dso-elf-abi-result-v1"
                && a.passed
                && a.scope == "versioned-elf-symbol-and-needed-closure"
                && &a.pairs == expected.pairs
                && a.source_manifest == self.source_manifest
                && a.toolchain_manifest == self.toolchain_manifest
                && a.checker_source.valid(false)
                && a.complete_tables.valid(false)
                && a.library_count == 11
                && a.original_main_exports > 0
                && a.original_main_exports == a.derived_main_exports
                && a.original_setup_exports > 0
                && a.original_setup_exports == a.derived_setup_exports
                && a.differing_defined_symbols == 0
                && a.unresolved_versioned_imports == 0
                && a.missing_needed_libraries == 0
                && a.unsupported_relocations == 0
                && a.executable_stack_or_wx_segments == 0
                && !a.cpp_layout_or_source_equivalence
                && !a.native_execution_qualified,
            "actual complete static ABI result bound to both derived and original libraries",
        )?;
        need(
            r.schema == "droidloom-native-two-dso-independent-retirement-v1"
                && r.passed
                && r.build_result == self.build_result.pin
                && r.abi_result == self.abi_result.pin
                && r.source_manifest == self.source_manifest
                && r.toolchain_manifest == self.toolchain_manifest
                && r.build_owner == b.owner
                && r.observer.valid()
                && (r.observer.pid, r.observer.start) != (b.owner.pid, b.owner.start)
                && r.observer.boot_id == b.owner.boot_id
                && r.observer.invocation != b.owner.invocation
                && r.original_build_generation_absent
                && r.original_cgroup_absent
                && r.all_command_generations_absent
                && r.original_inputs_unchanged
                && r.absolute_deadline_met,
            "independent actual retirement of this build and its complete child ledger",
        )?;
        Ok(ValidatedBuild { _private: () })
    }
    pub(crate) fn validate_tables_pin(&self, raw: &[u8]) -> Result<()> {
        let a: AbiResult = self.abi_result.parse()?;
        need(
            a.complete_tables == Pin::of(raw),
            "whole actual ABI table catalog",
        )
    }
    pub(crate) fn validate_surface_counts(&self, counts: [u64; 4]) -> Result<()> {
        let a: AbiResult = self.abi_result.parse()?;
        need(
            [
                a.original_main_exports,
                a.derived_main_exports,
                a.original_setup_exports,
                a.derived_setup_exports,
            ] == counts,
            "ABI report counts match independently parsed original ELF bodies",
        )
    }
    pub(crate) fn validate_inputs(&self, source: &[u8], toolchain: &[u8]) -> Result<()> {
        need(
            self.source_manifest == Pin::of(source)
                && self.toolchain_manifest == Pin::of(toolchain),
            "actual source/toolchain manifest bodies",
        )?;
        let source = manifest(source, "source")?;
        let toolchain = manifest(toolchain, "toolchain")?;
        let a: AbiResult = self.abi_result.parse()?;
        need(
            source.files.iter().any(|f| f.file == a.checker_source),
            "actual ABI checker belongs to the frozen source manifest",
        )?;
        let b: BuildResult = self.build_result.parse()?;
        for c in &b.commands {
            let names: &[&str] = match c.role {
                CommandRole::CompileCxx | CommandRole::CompileCrt => {
                    &["clang-r584948/bin/clang-22"]
                }
                CommandRole::Archive => &["clang-r584948/bin/llvm-ar"],
                CommandRole::LinkMain | CommandRole::LinkSetup => &["clang-r584948/bin/lld"],
                CommandRole::Inspect => &["host-tools/readelf", "host-tools/objdump"],
            };
            need(
                toolchain
                    .files
                    .iter()
                    .any(|f| names.contains(&f.path.as_str()) && f.file == c.program),
                "each actual command uses its fixed compiler/linker/inspection role",
            )?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    // Synthetic JSON for rejection tests only. No filesystem owner,
    // NativeResources, executed process, or Ready capability is constructed.
    fn negative_fixture() -> (Receipt, Pairs) {
        let artifact = |digit: char| Artifact {
            file: Pin {
                bytes: 128,
                sha256: digit.to_string().repeat(64),
            },
            build_id: digit.to_string().repeat(32),
        };
        let pairs = Pairs {
            original_main: artifact('1'),
            derived_main: artifact('2'),
            original_setup: artifact('3'),
            derived_setup: artifact('4'),
        };
        let source = Pin::of(b"synthetic source manifest");
        let toolchain = Pin::of(b"synthetic toolchain manifest");
        let owner = json!({"boot_id":"11111111-1111-1111-1111-111111111111","pid":100,
            "start":1000,"invocation":"1".repeat(32),"unit":"p4-native-v2-build-test.service"});
        let roles = [
            "compile_cxx",
            "compile_crt",
            "compile_crt",
            "archive",
            "link_main",
            "link_setup",
            "inspect",
        ];
        let commands: Vec<_> = roles
            .iter()
            .enumerate()
            .map(|(i, role)| {
                json!({"sequence":i,
            "role":role,"program":Pin::of(b"synthetic program"),"argv_sha256":"a".repeat(64),
            "pid":200+i,"start":2000+i,"waitid":{"pid":200+i,"code":1,"status":0},
            "pidfd_reaped":true,"stdout":Pin::of(b""),"stderr":Pin::of(b""),"duration_ns":1})
            })
            .collect();
        let build = RawReport::new(&serde_json::to_vec(&json!({
            "schema":"droidloom-native-two-dso-build-result-v1","passed":true,"owner":owner,
            "source_manifest":source,"toolchain_manifest":toolchain,"source_system_sha256":"5".repeat(64),
            "source_basis":"public-reference-not-source-equivalent","pairs":pairs,"commands":commands,
            "original_inputs_unchanged":true,"absolute_deadline_met":true,"native_execution_qualified":false,
            "source_equivalence_proved":false,"android_starts":0,"host_policy_loads":0})).unwrap()).unwrap();
        let abi = RawReport::new(&serde_json::to_vec(&json!({
            "schema":"droidloom-native-two-dso-elf-abi-result-v1","passed":true,"pairs":pairs,
            "source_manifest":source,"toolchain_manifest":toolchain,"scope":"versioned-elf-symbol-and-needed-closure",
            "checker_source":Pin::of(b"synthetic checker"),"complete_tables":Pin::of(b"synthetic tables"),
            "library_count":11,"original_main_exports":1,"derived_main_exports":1,
            "original_setup_exports":1,"derived_setup_exports":1,"differing_defined_symbols":0,
            "unresolved_versioned_imports":0,"missing_needed_libraries":0,"unsupported_relocations":0,
            "executable_stack_or_wx_segments":0,"cpp_layout_or_source_equivalence":false,
            "native_execution_qualified":false})).unwrap()).unwrap();
        let retired = RawReport::new(&serde_json::to_vec(&json!({
            "schema":"droidloom-native-two-dso-independent-retirement-v1","passed":true,
            "build_result":build.pin,"abi_result":abi.pin,"source_manifest":source,"toolchain_manifest":toolchain,
            "build_owner":owner,"observer":{"boot_id":"11111111-1111-1111-1111-111111111111","pid":101,
                "start":1001,"invocation":"2".repeat(32),"unit":"p4-native-v2-build-independent-test.service"},
            "original_build_generation_absent":true,"original_cgroup_absent":true,"all_command_generations_absent":true,
            "original_inputs_unchanged":true,"absolute_deadline_met":true})).unwrap()).unwrap();
        (
            Receipt {
                schema: "droidloom-native-build-receipt-v1".into(),
                source_manifest: source,
                toolchain_manifest: toolchain,
                build_result: build,
                abi_result: abi,
                retirement: retired,
            },
            pairs,
        )
    }
    fn rejection_reason(receipt: &Receipt, pairs: &Pairs) -> &'static str {
        receipt
            .validate(&Bindings {
                source_system_sha256: &"5".repeat(64),
                source_basis: "public-reference-not-source-equivalent",
                pairs,
            })
            .err()
            .expect("negative data must be rejected")
    }
    #[test]
    fn native_empty_build_objects_are_not_success_evidence() {
        assert!(
            RawReport::new(b"{}")
                .unwrap()
                .parse::<BuildResult>()
                .is_err()
        );
        assert!(RawReport::new(b"{}").unwrap().parse::<AbiResult>().is_err());
        assert!(
            RawReport::new(b"{}")
                .unwrap()
                .parse::<Retirement>()
                .is_err()
        );
        assert!(manifest(b"{}", "source").is_err());
        assert!(manifest(b"{}", "toolchain").is_err());
    }
    #[test]
    fn native_failed_child_and_foreign_derived_pair_are_rejected() {
        let (mut receipt, pairs) = negative_fixture();
        let mut raw: serde_json::Value = serde_json::from_str(&receipt.build_result.json).unwrap();
        raw["commands"][0]["waitid"]["status"] = 17.into();
        receipt.build_result = RawReport::new(&serde_json::to_vec(&raw).unwrap()).unwrap();
        let mut retired: serde_json::Value =
            serde_json::from_str(&receipt.retirement.json).unwrap();
        retired["build_result"] = serde_json::to_value(&receipt.build_result.pin).unwrap();
        receipt.retirement = RawReport::new(&serde_json::to_vec(&retired).unwrap()).unwrap();
        assert_eq!(
            rejection_reason(&receipt, &pairs),
            "real successful original child exit and bounded command identity"
        );
        let (receipt, mut pairs) = negative_fixture();
        pairs.derived_main.file.sha256 = "f".repeat(64);
        assert_eq!(
            rejection_reason(&receipt, &pairs),
            "actual successful two-DSO build, exact inputs and four artifact bindings"
        );
    }
    #[test]
    fn native_retirement_must_bind_original_generation_and_report_bytes() {
        let (mut receipt, pairs) = negative_fixture();
        let mut retired: serde_json::Value =
            serde_json::from_str(&receipt.retirement.json).unwrap();
        retired["build_owner"]["start"] = 9999.into();
        receipt.retirement = RawReport::new(&serde_json::to_vec(&retired).unwrap()).unwrap();
        assert_eq!(
            rejection_reason(&receipt, &pairs),
            "independent actual retirement of this build and its complete child ledger"
        );
        let (mut receipt, pairs) = negative_fixture();
        let mut retired: serde_json::Value =
            serde_json::from_str(&receipt.retirement.json).unwrap();
        retired["observer"]["invocation"] = retired["build_owner"]["invocation"].clone();
        receipt.retirement = RawReport::new(&serde_json::to_vec(&retired).unwrap()).unwrap();
        assert_eq!(
            rejection_reason(&receipt, &pairs),
            "independent actual retirement of this build and its complete child ledger"
        );
        let (mut receipt, pairs) = negative_fixture();
        receipt.build_result.json.push(' ');
        assert_eq!(
            rejection_reason(&receipt, &pairs),
            "complete native report bytes, not an unbound parsed claim"
        );
    }
}
