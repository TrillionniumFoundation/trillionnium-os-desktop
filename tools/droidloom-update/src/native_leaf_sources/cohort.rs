//! Fixed source-only successor of the recovered canonical leaf packet.
//!
//! Neither locations nor a historical receipt can choose output content or
//! confer runtime authority. The compiled recipe commits every output byte.
use super::*;

pub(super) const COHORT: &str = "cp3a-20261126-apps-r2";
pub(super) const ROOT: &str =
    "/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2";
const COHORT_RECIPE: &str =
    include_str!("../../../../android/manifest/native-application-leaf-cohort-r2.json");

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Content {
    bytes: u64,
    sha256: String,
}
#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Patch {
    offset: usize,
    remove: String,
    insert: String,
}
#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Member {
    relative_path: String,
    recovered_member: Option<String>,
    embedded_source: Option<String>,
    before: Content,
    patches: Vec<Patch>,
    output: Pin,
    historical_evidence_only: bool,
    fixed_binary_input: bool,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct CohortRecipe {
    schema: String,
    cohort: String,
    historical_cohort_root: String,
    canonical_root: String,
    recovery_recipe: Pin,
    source_manifest: Pin,
    input_file_count: usize,
    recovered_source_input_count: usize,
    helper_binary: Pin,
    helper_staging_mode: u32,
    output_file_count: usize,
    output_bytes: u64,
    preparation_count: usize,
    unique_entry_count: usize,
    members: Vec<Member>,
    semantic_changes: Vec<Value>,
    settings_v3: Value,
    ihg_material: Value,
    runtime_prerequisites: Vec<String>,
    source_only: bool,
    installation_authorized: bool,
    runtime_qualified: bool,
    #[serde(rename = "Main_qualified")]
    main_qualified: bool,
    whole_app_business_accepted: bool,
    production_ready: bool,
}

fn embedded(name: &str) -> Result<&'static [u8]> {
    Ok(match name {
        "settings_case.py" => {
            include_bytes!("../../resources/native-leaves/cp3a-20261126-apps-r2/settings_case.py")
        }
        "settings_runtime.py" => include_bytes!(
            "../../resources/native-leaves/cp3a-20261126-apps-r2/settings_runtime.py"
        ),
        "settings_guard.py" => {
            include_bytes!("../../resources/native-leaves/cp3a-20261126-apps-r2/settings_guard.py")
        }
        "settings_policy.py" => {
            include_bytes!("../../resources/native-leaves/cp3a-20261126-apps-r2/settings_policy.py")
        }
        "settings_profiles.py" => include_bytes!(
            "../../resources/native-leaves/cp3a-20261126-apps-r2/settings_profiles.py"
        ),
        "settings_entry.py" => {
            include_bytes!("../../resources/native-leaves/cp3a-20261126-apps-r2/settings_entry.py")
        }
        "settings_roundtrip.py" => include_bytes!(
            "../../resources/native-leaves/cp3a-20261126-apps-r2/settings_roundtrip.py"
        ),
        _ => return fail("unlisted embedded leaf source"),
    })
}

fn fixed_recipe() -> Result<CohortRecipe> {
    let r: CohortRecipe = serde_json::from_str(COHORT_RECIPE)?;
    if r.schema != "droidloom.native-leaf-cohort-source-recipe.v1"
        || r.cohort != COHORT
        || r.canonical_root != ROOT
        || r.historical_cohort_root
            != "/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261120-apps-r1"
        || r.input_file_count != 477
        || r.recovered_source_input_count != 476
        || r.output_file_count != 476
        || r.helper_binary.path != "held-namespace-entry"
        || r.helper_binary.bytes != FIXED_HELPER_BYTES
        || r.helper_binary.sha256 != FIXED_HELPER_SHA256
        || r.helper_staging_mode != 0o400
        || r.members.len() != r.output_file_count
        || r.output_bytes > MAX_TOTAL
        || r.preparation_count != 14
        || r.unique_entry_count != 10
        || !r.source_only
        || r.installation_authorized
        || r.runtime_qualified
        || r.main_qualified
        || r.whole_app_business_accepted
        || r.production_ready
        || r.runtime_prerequisites.len() != 6
    {
        return fail("invalid source-only successor recipe");
    }
    check_bytes(RECIPE.as_bytes(), &r.recovery_recipe)?;
    let recovery: Recipe = serde_json::from_str(RECIPE)?;
    if r.source_manifest != recovery.source_manifest {
        return fail("successor must consume the exact recovered source manifest");
    }
    let mut names = BTreeSet::new();
    let mut origins = BTreeSet::new();
    let mut embedded_names = BTreeSet::new();
    let mut total = 0u64;
    let mut new_sources = 0;
    let mut binaries = 0;
    for row in &r.members {
        relative(&row.relative_path)?;
        if row.output.path != format!("{ROOT}/{}", row.relative_path)
            || ((row.output.bytes > MAX_FILE || row.before.bytes > MAX_FILE)
                && !row.fixed_binary_input)
            || !sha_shape(&row.output.sha256)
            || !sha_shape(&row.before.sha256)
            || !names.insert(row.relative_path.clone())
            || row.patches.len() > 512
            || row.historical_evidence_only
                != (row.relative_path.starts_with("inputs/")
                    || row.relative_path.starts_with("evidence/"))
        {
            return fail("invalid, duplicate, or oversized fixed successor member");
        }
        total = total
            .checked_add(row.output.bytes)
            .ok_or("successor byte count overflow")?;
        if row.fixed_binary_input {
            binaries += 1;
            if row.relative_path != "bin/held-namespace-entry"
                || row.recovered_member.is_some()
                || row.embedded_source.is_some()
                || !row.patches.is_empty()
                || row.before.bytes != FIXED_HELPER_BYTES
                || row.before.sha256 != FIXED_HELPER_SHA256
                || row.output.bytes != FIXED_HELPER_BYTES
                || row.output.sha256 != FIXED_HELPER_SHA256
            {
                return fail("helper is not the single source-owned admitted ELF");
            }
        }
        match &row.recovered_member {
            Some(origin) => {
                if origin != &format!("bundle/{}", row.relative_path)
                    || !origins.insert(origin.clone())
                {
                    return fail("successor origin changed or reused");
                }
            }
            None if row.fixed_binary_input => {}
            None => {
                new_sources += 1;
                if row.relative_path != "source/settings/settings_roundtrip.py"
                    || row.embedded_source.as_deref() != Some("settings_roundtrip.py")
                {
                    return fail("unreviewed new leaf source");
                }
            }
        }
        if let Some(name) = &row.embedded_source {
            if row.relative_path != format!("source/settings/{name}")
                || !embedded_names.insert(name.clone())
            {
                return fail("embedded leaf source used outside its fixed member");
            }
            let raw = embedded(name)?;
            if raw.len() as u64 != row.before.bytes || digest(raw) != row.before.sha256 {
                return fail("embedded leaf source and recipe differ");
            }
        }
        if row.historical_evidence_only
            && row.relative_path != "evidence/helper/evidence-manifest.json"
            && (!row.patches.is_empty()
                || row.embedded_source.is_some()
                || row.before.bytes != row.output.bytes
                || row.before.sha256 != row.output.sha256)
        {
            return fail(
                "historical input or evidence cannot be rewritten as successor qualification",
            );
        }
    }
    if origins.len() != 474
        || new_sources != 1
        || binaries != 1
        || embedded_names.len() != 7
        || total != r.output_bytes
    {
        return fail("fixed successor source closure differs");
    }
    Ok(r)
}

fn apply_patches(raw: &[u8], row: &Member) -> Result<Vec<u8>> {
    if raw.len() as u64 != row.before.bytes || digest(raw) != row.before.sha256 {
        return fail("successor patch input is not the fixed source");
    }
    if row.fixed_binary_input {
        if row.relative_path != "bin/held-namespace-entry"
            || !row.patches.is_empty()
            || raw.len() as u64 != FIXED_HELPER_BYTES
            || digest(raw) != FIXED_HELPER_SHA256
        {
            return fail("helper cannot be patched or substituted");
        }
        check_bytes(raw, &row.output)?;
        return Ok(raw.to_vec());
    }
    let mut out = Vec::new();
    let mut cursor = 0usize;
    for patch in &row.patches {
        let end = patch
            .offset
            .checked_add(patch.remove.len())
            .ok_or("patch offset overflow")?;
        if patch.offset < cursor
            || end > raw.len()
            || raw.get(patch.offset..end) != Some(patch.remove.as_bytes())
        {
            return fail("successor patch is out of order or its exact preimage differs");
        }
        if out
            .len()
            .checked_add(patch.offset - cursor)
            .and_then(|n| n.checked_add(patch.insert.len()))
            .is_none_or(|n| n as u64 > MAX_FILE)
        {
            return fail("successor patch output bound exceeded");
        }
        out.extend_from_slice(&raw[cursor..patch.offset]);
        out.extend_from_slice(patch.insert.as_bytes());
        cursor = end;
    }
    if out
        .len()
        .checked_add(raw.len() - cursor)
        .is_none_or(|n| n as u64 > MAX_FILE)
    {
        return fail("successor output bound exceeded");
    }
    out.extend_from_slice(&raw[cursor..]);
    check_bytes(&out, &row.output)?;
    Ok(out)
}

fn check_named_pin(pin: &Pin, outputs: &BTreeMap<String, Vec<u8>>) -> Result<()> {
    let name = pin
        .path
        .strip_prefix(&format!("{ROOT}/"))
        .ok_or("live leaf pin escaped the new cohort")?;
    relative(name)?;
    check_bytes(outputs.get(name).ok_or("missing named leaf source")?, pin)
}

fn check_json_pins(
    value: &Value,
    outputs: &BTreeMap<String, Vec<u8>>,
    depth: usize,
) -> Result<usize> {
    if depth > 64 {
        return fail("leaf source JSON nesting bound");
    }
    match value {
        Value::Object(map) => {
            if let (Some(path), Some(_), Some(_)) = (
                map.get("path").and_then(Value::as_str),
                map.get("bytes"),
                map.get("sha256"),
            ) {
                if path.starts_with(ROOT) {
                    let p: Pin = serde_json::from_value(
                        json!({"path":path,"bytes":map["bytes"],"sha256":map["sha256"]}),
                    )?;
                    check_named_pin(&p, outputs)?;
                    return Ok(1);
                }
                if path.starts_with("/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261120-apps-r1/") {
                    return fail("live successor still names a historical canonical source");
                }
                return Ok(0); // Original external source/evidence pins retain their identity.
            }
            map.values().try_fold(0usize, |n, v| {
                Ok(n + check_json_pins(v, outputs, depth + 1)?)
            })
        }
        Value::Array(values) => values.iter().try_fold(0usize, |n, v| {
            Ok(n + check_json_pins(v, outputs, depth + 1)?)
        }),
        _ => Ok(0),
    }
}

fn validate_cohort(outputs: &BTreeMap<String, Vec<u8>>) -> Result<Value> {
    if outputs.len() != 476 {
        return fail("incomplete successor member set");
    }
    let catalog: Vec<CurrentLeaf> = serde_json::from_slice(
        outputs
            .get("selection/leaf_sources.json")
            .ok_or("missing source catalog")?,
    )?;
    if catalog.len() != 14 {
        return fail("exact fourteen-entry source catalog required");
    }
    let mut entries = BTreeSet::new();
    let mut preparations = BTreeSet::new();
    for (index, row) in catalog.iter().enumerate() {
        if row.index != index
            || !row.entry.path.starts_with(&format!("{ROOT}/source/"))
            || !row
                .preparation
                .path
                .starts_with(&format!("{ROOT}/preparations/"))
            || !preparations.insert(row.preparation.path.clone())
        {
            return fail("source catalog order, entry, or preparation differs");
        }
        check_named_pin(&row.entry, outputs)?;
        check_named_pin(&row.preparation, outputs)?;
        entries.insert(row.entry.path.clone());
    }
    if entries.len() != 10 {
        return fail("exact ten unique source entries required");
    }
    let selection: Value = serde_json::from_slice(
        outputs
            .get("selection/selection-14.json")
            .ok_or("missing source selection")?,
    )?;
    let selected: Vec<Pin> = serde_json::from_value(
        selection
            .get("selected_preparations")
            .ok_or("missing selected preparation pins")?
            .clone(),
    )?;
    if selected.len() != catalog.len()
        || selected
            .iter()
            .zip(&catalog)
            .any(|(p, c)| p != &c.preparation)
        || selection.get("runtime_qualified") != Some(&Value::Bool(false))
        || selection.get("historical_runtime_credit_transferred") != Some(&Value::Bool(false))
        || selection.get("new_runtime_acceptance_count") != Some(&json!(0))
        || selection.get("production_ready") != Some(&Value::Bool(false))
    {
        return fail("new source selection cannot transfer historical runtime credit");
    }
    let mut checked = 0usize;
    for (name, raw) in outputs {
        if name.ends_with(".json") && !name.starts_with("inputs/") && !name.starts_with("evidence/")
        {
            let value: Value = serde_json::from_slice(raw)?;
            checked += check_json_pins(&value, outputs, 0)?;
        }
    }
    Ok(
        json!({"preparations":preparations.len(),"unique_entries":entries.len(),
        "named_json_source_pins_verified":checked,"selection_matches_catalog":true,
        "source_catalog_complete":true,"installed":false,"runtime_qualified":false,
        "whole_app_business_accepted":false}),
    )
}

/// Materialize the entire reviewed successor source closure into one fresh
/// ordinary-user staging directory. No subprocess, installation or leaf runs.
pub(crate) fn materialize(input: &Path, helper: &Path, output: &Path) -> Result<Value> {
    if unsafe { libc::getuid() } == 0
        || unsafe { libc::geteuid() } == 0
        || unsafe { libc::getuid() } != unsafe { libc::geteuid() }
    {
        return fail("materialize the leaf cohort as the ordinary build user");
    }
    absolute(input)?;
    absolute(helper)?;
    absolute(output)?;
    if input.starts_with(output) || output.starts_with(input) {
        return fail("independent recovered input and fresh successor staging required");
    }
    let r = fixed_recipe()?;
    if helper.file_name().and_then(|n| n.to_str()) != Some("held-namespace-entry")
        || helper.starts_with(output)
        || output.starts_with(helper)
    {
        return fail("fixed helper filename and independent output required");
    }
    let helper_source = InputTree::open(helper.parent().ok_or("helper parent missing")?)?;
    let mut helper_file = Held::open(
        &helper_source.root,
        "held-namespace-entry",
        &r.helper_binary,
    )?;
    let helper_bytes = helper_file.bytes()?;
    if helper_bytes.get(..7) != Some(b"\x7fELF\x02\x01\x01".as_slice())
        || helper_bytes.get(18..20) != Some(b"\x3e\x00".as_slice())
    {
        return fail("admitted helper is not the fixed x86_64 ELF");
    }
    let recovery: Recipe = serde_json::from_str(RECIPE)?;
    let mut source = InputTree::open(input)?;
    let mut manifest = Held::open(&source.root, &r.source_manifest.path, &r.source_manifest)?;
    let parsed: SourceManifest = serde_json::from_slice(&manifest.bytes()?)?;
    let expected = expected_files(&recovery, &parsed)?;
    if source.inventory()? != expected.keys().cloned().collect() {
        return fail("recovered input closure has an extra or missing member");
    }
    let mut held = BTreeMap::new();
    for (name, pin) in &expected {
        held.insert(name.clone(), Held::open(&source.root, name, pin)?);
    }
    let required: BTreeSet<_> = r
        .members
        .iter()
        .filter_map(|m| m.recovered_member.clone())
        .collect();
    let original: BTreeSet<_> = expected
        .keys()
        .filter(|n| n.starts_with("bundle/"))
        .cloned()
        .collect();
    if required != original {
        return fail("successor omitted or invented a recovered origin");
    }
    let mut outputs = BTreeMap::new();
    for row in &r.members {
        let raw = if row.fixed_binary_input {
            helper_bytes.clone()
        } else if let Some(name) = &row.embedded_source {
            embedded(name)?.to_vec()
        } else {
            held.get_mut(
                row.recovered_member
                    .as_ref()
                    .ok_or("missing fixed source origin")?,
            )
            .ok_or("unheld source origin")?
            .bytes()?
        };
        let result = apply_patches(&raw, row)?;
        outputs.insert(row.relative_path.clone(), result);
    }
    let closure = validate_cohort(&outputs)?;
    for file in held.values_mut() {
        file.recheck(&source.root)?;
    }
    source.recheck()?;
    helper_file.recheck(&helper_source.root)?;
    helper_source.recheck()?;
    let expected_members = installed_members()?;
    let archive_bytes = super::package::build(&outputs, &expected_members)?;
    let destination = OutputTree::create(output)?;
    let mut written = Vec::new();
    for (name, raw) in &outputs {
        written.push(destination.write(&format!("cohort/{name}"), raw)?);
    }
    written.push(destination.write("SOURCE-RECIPE.json", COHORT_RECIPE.as_bytes())?);
    let archive = super::package::write_output(&destination, &archive_bytes, &expected_members)?;
    destination.recheck(&written)?;
    let mut input_rows = Vec::new();
    for file in held.values_mut() {
        file.recheck(&source.root)?;
        input_rows.push(json!({"relative_path":file.name,"pin":file.pin,"identity":file.before}));
    }
    manifest.recheck(&source.root)?;
    source.recheck()?;
    helper_file.recheck(&helper_source.root)?;
    helper_source.recheck()?;
    input_rows.push(json!({"relative_path":"held-namespace-entry","pin":helper_file.pin,"identity":helper_file.before,
        "path":helper,"kind":"fixed_historical_normal_ELF","new_rebuild_c325_selected":false}));
    let report = json!({
        "schema":"droidloom.native-leaf-cohort-source-materialization.v1",
        "state":"SOURCE_COHORT_COMPLETE_RUNTIME_PREREQUISITES_REQUIRED",
        "cohort":COHORT,"canonical_root":ROOT,"input_root":input,"staging_root":output,
        "source_recipe":{"bytes":COHORT_RECIPE.len(),"sha256":digest(COHORT_RECIPE.as_bytes())},
        "source_manifest":r.source_manifest,"input_files":input_rows,"output_files":written,
        "input_count":held.len()+1,"recovered_source_input_count":held.len(),"cohort_file_count":outputs.len(),"cohort_bytes":r.output_bytes,
        "package":{"path":output.join("COHORT.tar"),"pin":archive,"format":"canonical-ustar","member_count":outputs.len(),"root_owner_required_for_directory_input":true,"ordinary_public_archive_import_supported":true},
        "closure":closure,"semantic_changes":r.semantic_changes,"settings_v3":r.settings_v3,
        "ihg_material":r.ihg_material,"runtime_prerequisites":r.runtime_prerequisites,
        "full_source_bookends_equal":true,"output_full_readback":true,
        "source_only":true,"installation_performed":false,"leaf_execution_performed":false,
        "native_helper_binary_deployed":false,"Main_qualified":false,"runtime_qualified":false,
        "whole_app_business_accepted":false,"accepted_application_count":0,
        "historical_runtime_authority_transferred":false,"production_ready":false
    });
    let mut body = serde_json::to_vec_pretty(&report)?;
    body.push(b'\n');
    let result = destination.write("NATIVE-LEAF-COHORT.json", &body)?;
    destination.recheck(&[result])?;
    super::package::recheck_output(&destination, &archive)?;
    for file in held.values_mut() {
        file.recheck(&source.root)?;
    }
    source.recheck()?;
    helper_file.recheck(&helper_source.root)?;
    helper_source.recheck()?;
    Ok(report)
}

pub(super) fn installed_members() -> Result<BTreeMap<String, Pin>> {
    let r = fixed_recipe()?;
    Ok(r.members
        .into_iter()
        .map(|m| (m.relative_path, m.output))
        .collect())
}
pub(super) fn compiled_recipe_pin() -> Value {
    json!({"bytes":COHORT_RECIPE.len(),"sha256":digest(COHORT_RECIPE.as_bytes())})
}

#[cfg(test)]
mod tests {
    use super::*;

    fn member(raw: &[u8], result: &[u8], patches: Vec<Patch>) -> Member {
        Member {
            relative_path: "source/example.py".into(),
            recovered_member: Some("bundle/source/example.py".into()),
            embedded_source: None,
            before: Content {
                bytes: raw.len() as u64,
                sha256: digest(raw),
            },
            patches,
            output: Pin {
                path: format!("{ROOT}/source/example.py"),
                bytes: result.len() as u64,
                sha256: digest(result),
            },
            historical_evidence_only: false,
            fixed_binary_input: false,
        }
    }

    #[test]
    fn patches_require_exact_preimages_and_complete_expected_output() {
        let row = member(
            b"first\nold\nlast\n",
            b"first\nnew\nlast\n",
            vec![Patch {
                offset: 6,
                remove: "old\n".into(),
                insert: "new\n".into(),
            }],
        );
        assert_eq!(
            apply_patches(b"first\nold\nlast\n", &row).unwrap(),
            b"first\nnew\nlast\n"
        );
        assert!(apply_patches(b"first\nOLD\nlast\n", &row).is_err());
        let mut bad = row.clone();
        bad.output.sha256 = digest(b"other");
        assert!(apply_patches(b"first\nold\nlast\n", &bad).is_err());
        let mut bad = row.clone();
        bad.patches[0].offset = 7;
        assert!(apply_patches(b"first\nold\nlast\n", &bad).is_err());
    }

    #[test]
    fn patches_cannot_overlap_or_escape_the_source() {
        let raw = b"abcd";
        let row = member(
            raw,
            b"unused",
            vec![
                Patch {
                    offset: 1,
                    remove: "bc".into(),
                    insert: "B".into(),
                },
                Patch {
                    offset: 2,
                    remove: "c".into(),
                    insert: "C".into(),
                },
            ],
        );
        assert!(apply_patches(raw, &row).is_err());
        let row = member(
            raw,
            b"unused",
            vec![Patch {
                offset: usize::MAX,
                remove: "x".into(),
                insert: "".into(),
            }],
        );
        assert!(apply_patches(raw, &row).is_err());
    }

    #[test]
    fn compiled_successor_has_only_exact_source_owned_members() {
        let r = fixed_recipe().unwrap();
        assert_eq!(r.members.len(), 476);
        assert_eq!(
            r.members
                .iter()
                .filter(|m| m.embedded_source.is_some())
                .count(),
            7
        );
        assert_eq!(
            r.members
                .iter()
                .filter(|m| m.recovered_member.is_none())
                .count(),
            2
        );
        assert!(embedded("../settings_case.py").is_err());
    }

    #[test]
    fn named_source_pins_reject_stale_paths_and_altered_bytes() {
        let outputs = BTreeMap::from([("source/test.py".to_string(), b"source".to_vec())]);
        let valid =
            json!({"path":format!("{ROOT}/source/test.py"),"bytes":6,"sha256":digest(b"source")});
        assert_eq!(check_json_pins(&valid, &outputs, 0).unwrap(), 1);
        let mut bad = valid.clone();
        bad["sha256"] = json!(digest(b"fake"));
        assert!(check_json_pins(&bad, &outputs, 0).is_err());
        let mut bad = valid.clone();
        bad["path"] = json!(
            "/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261120-apps-r1/source/test.py"
        );
        assert!(check_json_pins(&bad, &outputs, 0).is_err());
    }
}
