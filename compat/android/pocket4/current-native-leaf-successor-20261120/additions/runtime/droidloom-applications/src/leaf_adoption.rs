//! Explicit root publication of an already built native/source pairing.
//!
//! The root-owned intent carries independently reviewed CI artifact pins and
//! the actual full CURRENT preimage/F9 expected by the operator. Publication
//! holds the original exclusive locks, copies the actual bytes, then changes
//! exactly one CURRENT field with a fresh full-byte CAS. It installs nothing.
use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::os::fd::AsRawFd;
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt, chown};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use droidloom_supervisor::control::NativeApplicationSourceLocks;
use serde::Deserialize;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

use super::{FilePin, leaf_release, leaf_routes};
use leaf_release::{CLI, CURRENT, Inputs, Manifest, Preimage, ROOT, body, f9};

const EXPECTED_ORDINARY_TESTS:u64=1588;
const EXPECTED_RELEASES:[&str;19]=[
    "droidloom-applications",
    "droidloom-classpath-wrapper",
    "droidloom-dmabuf-probe",
    "droidloom-doctor",
    "droidloom-gapps",
    "droidloom-host-mac",
    "droidloom-image",
    "droidloom-mesa",
    "droidloom-package",
    "droidloom-package-helper",
    "droidloom-runtime-inputs",
    "droidloom-source",
    "droidloom-supervisor",
    "droidloom-task-launcher",
    "droidloom-translation-bench",
    "droidloom-update",
    "droidloom-wayland",
    "droidloomctl",
    "droidloomd",
];

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Intent {
    schema: String,
    expected_current: Preimage,
    binary: FilePin,
    selection: FilePin,
    ci_report: FilePin,
    source_tree: String,
    ci_commit: String,
    ci_run_id: u64,
    runtime_qualified: bool,
    production_ready: bool,
}

fn require(ok:bool,message:&str) -> Result<(),String> {
    if ok { Ok(()) } else { Err(message.into()) }
}

fn owner_window(expiry:u64) -> Result<(),String> {
    let now=SystemTime::now().duration_since(UNIX_EPOCH).map_err(|e|e.to_string())?.as_secs();
    require(expiry>now.saturating_add(1530+60),"original owner window cannot cover adoption and a complete leaf")
}

fn reference(path:PathBuf,raw:&[u8]) -> FilePin {
    FilePin {path,bytes:raw.len() as u64,sha256:hex::encode(Sha256::digest(raw))}
}

fn content_file(folder:&str,raw:&[u8]) -> Result<FilePin,String> {
    let result=reference(PathBuf::from(format!("{ROOT}/{folder}/{}.json",hex::encode(Sha256::digest(raw)))),raw);
    // The administrator's deployment layout must already contain each private
    // root-owned directory. Never create or relax a shared parent here.
    let parent=result.path.parent().ok_or("release publication parent missing")?;
    let mut custody=Inputs::new();
    let sentinel=parent.join(".layout");
    let marker=custody.read(&sentinel,None,64,true,false)?;
    require(marker==b"pocket4-native-application-leaf-layout-v1\n","root deployment layout marker differs")?;
    custody.guard()?;
    let anchored=custody.anchored(&result.path)?;
    match OpenOptions::new().write(true).create_new(true).mode(0o400).custom_flags(0x20000).open(&anchored) {
        Ok(mut file) => {
            file.write_all(raw).and_then(|()|file.sync_all()).map_err(|e|e.to_string())?;
            chown(format!("/proc/self/fd/{}",file.as_raw_fd()),Some(0),Some(0)).map_err(|e|e.to_string())?;
            custody.sync_parent(&result.path)?;
        }
        Err(error) if error.kind()==std::io::ErrorKind::AlreadyExists => {},
        Err(error) => return Err(error.to_string()),
    }
    custody.read(&result.path,Some(&result),2*1024*1024,true,false)?;
    custody.guard()?;
    Ok(result)
}

fn checked_ci(value:&Value,intent:&Intent) -> Result<(),String> {
    let binaries=value["fresh_release_binaries"].as_object().ok_or("complete CI release binaries absent")?;
    let binary=&value["fresh_release_binaries"]["droidloom-applications"];
    require(value["state"]=="ALL_CURRENT_ORDINARY_AND19_NORMAL_RELEASE_BUILDS_PASSED"
        && value["source_tree"]==intent.source_tree && value["github_commit"]==intent.ci_commit
        && value["github_run_id"].as_u64()==Some(intent.ci_run_id)
        && value["all_source_bookends_equal"]==true && value["all_input_packet_bookends_equal"]==true
        && value["fresh_ordinary_passed"].as_u64()==Some(EXPECTED_ORDINARY_TESTS)
        && value["fresh_test_targets"].as_u64()==Some(49)
        && binaries.keys().map(String::as_str).collect::<Vec<_>>()==EXPECTED_RELEASES
        && value["fresh_example_binaries"].as_object().is_some_and(|items|items.len()==3)
        && value["doc_targets_checked"].as_array().is_some_and(|items|items.len()==20)
        && value["doc_test_commands_executed"]==true
        && value["fresh_doc_tests_passed"].as_u64()==Some(0)
        && binary["bytes"].as_u64()==Some(intent.binary.bytes) && binary["sha256"]==intent.binary.sha256
        && value["fresh_example_tests_passed"].as_u64()==Some(9)
        && value["errors"].as_array().is_some_and(Vec::is_empty)
        && value["final_descendant_retirement"].as_array().is_some_and(Vec::is_empty),
        "reviewed full current source CI report does not bind this actual final executable")
}

pub(super) fn adopt(path:&Path,expected_sha:&str) -> Result<Value,String> {
    require(expected_sha.len()==64 && expected_sha.bytes().all(|c|c.is_ascii_digit()||(b'a'..=b'f').contains(&c))
        && path.to_str()==Some(format!("{ROOT}/adoption-intents/{expected_sha}.json").as_str()),
        "explicit pinned root-owned adoption intent required")?;
    let locks=NativeApplicationSourceLocks::acquire_for_adoption().map_err(|e|e.to_string())?;
    let mut inputs=Inputs::new();
    let raw=inputs.read(path,None,65536,true,false)?;
    require(hex::encode(Sha256::digest(&raw))==expected_sha,"adoption intent differs from independent caller pin")?;
    let intent:Intent=serde_json::from_value(leaf_release::json(&raw)?).map_err(|e|e.to_string())?;
    require(intent.schema=="pocket4-native-application-leaf-adoption-intent-v1"
        && !intent.runtime_qualified && !intent.production_ready,"adoption cannot grant runtime or application qualification")?;
    let (selection,catalog)=leaf_routes::compiled_release_sources();
    require(intent.selection==selection && intent.binary.path.to_str()==Some(CLI)
        && intent.expected_current.path.to_str()==Some(CURRENT),"adoption intent must retain compiled source selection and canonical files")?;
    leaf_routes::validate_selection(&selection)?;
    inputs.read(&selection.path,Some(&selection),1024*1024,false,false)?;
    let before_pin=FilePin {path:CURRENT.into(),bytes:intent.expected_current.bytes,sha256:intent.expected_current.sha256.clone()};
    let before_raw=inputs.read(Path::new(CURRENT),Some(&before_pin),2*1024*1024,false,false)?;
    require(inputs.identity(Path::new(CURRENT))?==intent.expected_current.f9,"actual complete CURRENT F9 differs from externally reviewed preimage")?;
    let before=leaf_release::json(&before_raw)?;
    require(before["application_qualification_preparations"]==serde_json::to_value(&selection).map_err(|e|e.to_string())?,"compiled source selection must already be formally selected")?;
    inputs.read(Path::new(CLI),Some(&intent.binary),64*1024*1024,true,true)?;
    let actual_exe=File::open("/proc/self/exe").map_err(|e|e.to_string())?;
    let exe_identity=f9(&actual_exe.metadata().map_err(|e|e.to_string())?)?;
    require(exe_identity==inputs.identity(Path::new(CLI))?
        && hex::encode(Sha256::digest(body(&actual_exe,exe_identity[6])?))==intent.binary.sha256
        && f9(&actual_exe.metadata().map_err(|e|e.to_string())?)?==exe_identity,
        "publisher must run the actual final CI executable installed at the canonical path")?;
    let ci=leaf_release::json(&inputs.read(&intent.ci_report.path,Some(&intent.ci_report),64*1024*1024,false,false)?)?;
    checked_ci(&ci,&intent)?;
    let catalog_pin=content_file("catalogs",catalog.as_bytes())?;
    let before_copy=content_file("current-preimages",&before_raw)?;
    let owner:leaf_release::Owner=serde_json::from_value(before["foreground_owner"].clone()).map_err(|e|e.to_string())?;
    let owner_expiry=owner.expiry()?;
    owner_window(owner_expiry)?;
    let manifest=Manifest {schema:"pocket4-native-application-leaf-release-v1".into(),protocol:leaf_release::PROTOCOL.into(),
        binary:intent.binary,selection,catalog:catalog_pin,foreground_owner:owner,
        owner_expires_unix_seconds:owner_expiry,before_current:intent.expected_current,
        before_current_copy:before_copy,source_tree:intent.source_tree,ci_commit:intent.ci_commit,ci_run_id:intent.ci_run_id,
        runtime_qualified:false,production_ready:false};
    manifest.validate()?;
    let mut manifest_raw=serde_json::to_vec(&manifest).map_err(|e|e.to_string())?; manifest_raw.push(b'\n');
    let release=content_file("releases",&manifest_raw)?;
    let mut after=before.clone();
    after.as_object_mut().ok_or("CURRENT must be one complete object")?.insert("native_application_leaf_release".into(),json!(release));
    let mut after_raw=serde_json::to_vec(&after).map_err(|e|e.to_string())?; after_raw.push(b'\n');
    require(after_raw.len()<2*1024*1024,"compact canonical CURRENT must remain below the original reader bound")?;
    let current_parent=Path::new(CURRENT).parent().ok_or("CURRENT parent absent")?;
    let temporary=current_parent.join(format!(".native-leaf-adoption-{}-{}.new",std::process::id(),release.sha256));
    inputs.guard()?; locks.validate().map_err(|e|e.to_string())?;
    let anchored_temporary=inputs.anchored(&temporary)?;
    let anchored_current=inputs.anchored(Path::new(CURRENT))?;
    let mut file=OpenOptions::new().write(true).read(true).create_new(true).mode(0o600).custom_flags(0x20000)
        .open(&anchored_temporary).map_err(|e|e.to_string())?;
    file.write_all(&after_raw).and_then(|()|file.sync_all()).map_err(|e|e.to_string())?;
    chown(format!("/proc/self/fd/{}",file.as_raw_fd()),Some(1000),Some(1000)).map_err(|e|e.to_string())?;
    file.set_permissions(fs::Permissions::from_mode(0o600)).map_err(|e|e.to_string())?;
    file.sync_all().map_err(|e|e.to_string())?;
    let temporary_identity=f9(&file.metadata().map_err(|e|e.to_string())?)?;
    require(f9(&fs::symlink_metadata(&temporary).map_err(|e|e.to_string())?)?==temporary_identity
        && f9(&fs::symlink_metadata(&anchored_temporary).map_err(|e|e.to_string())?)?==temporary_identity
        && body(&file,after_raw.len() as u64)?==after_raw,"new CURRENT body or temporary inode changed before CAS")?;
    // This is the actual original FD/raw hash/F9 recheck, under both original
    // exclusive OFDs. No field is deleted to manufacture a historical proof.
    inputs.guard()?;
    locks.validate().map_err(|e|e.to_string())?;
    owner_window(manifest.owner_expires_unix_seconds)?;
    fs::rename(&anchored_temporary,&anchored_current).map_err(|e|e.to_string())?;
    inputs.sync_parent(Path::new(CURRENT))?;
    let mut readback=Inputs::new();
    let after_pin=reference(CURRENT.into(),&after_raw);
    let observed=readback.read(Path::new(CURRENT),Some(&after_pin),2*1024*1024,false,false)?;
    require(observed==after_raw && leaf_release::json(&observed)?==after
        && readback.identity(Path::new(CURRENT))?==f9(&file.metadata().map_err(|e|e.to_string())?)?,
        "whole CURRENT adoption readback or actual committed inode differs")?;
    readback.read(&release.path,Some(&release),65536,true,false)?;
    readback.read(&manifest.before_current_copy.path,Some(&manifest.before_current_copy),2*1024*1024,true,false)?;
    readback.read(Path::new(CLI),Some(&manifest.binary),64*1024*1024,true,true)?;
    readback.guard()?; locks.validate().map_err(|e|e.to_string())?;
    owner_window(manifest.owner_expires_unix_seconds)?;
    Ok(json!({"schema":"pocket4-native-application-leaf-adoption-result-v1",
        "before_current":manifest.before_current,"after_current":after_pin,
        "after_current_f9":readback.identity(Path::new(CURRENT))?,"release":release,
        "changed_paths":["/native_application_leaf_release"],"whole_current_readback_verified":true,
        "owner_and_expiry_unchanged":true,"Android_actions":0,"runtime_qualified":false,"production_ready":false}))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn adoption_intent_requires_exact_typed_root_reviewed_inputs() {
        let data=json!({"schema":"pocket4-native-application-leaf-adoption-intent-v1",
            "expected_current":{"path":CURRENT,"bytes":1,"sha256":"a".repeat(64),"f9":[1,2,33152,1000,1000,1,1,3,4]},
            "binary":{"path":CLI,"bytes":1,"sha256":"b".repeat(64)},
            "selection":{"path":"/selection","bytes":1,"sha256":"c".repeat(64)},
            "ci_report":{"path":"/report","bytes":1,"sha256":"d".repeat(64)},
            "source_tree":"a".repeat(40),"ci_commit":"b".repeat(40),"ci_run_id":1,
            "runtime_qualified":false,"production_ready":false});
        assert!(serde_json::from_value::<Intent>(data.clone()).is_ok());
        for key in ["ci_run_id","runtime_qualified","production_ready"] {
            let mut changed=data.clone(); changed[key]=if key=="ci_run_id" {json!(true)} else {json!(0)};
            assert!(serde_json::from_value::<Intent>(changed).is_err());
        }
        let mut changed=data; changed["allow_unreviewed_current"]=json!(true);
        assert!(serde_json::from_value::<Intent>(changed).is_err());
    }
}
