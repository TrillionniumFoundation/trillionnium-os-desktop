#![deny(unsafe_op_in_unsafe_fn)]
use serde::Serialize;
use std::collections::BTreeMap;
use std::fs;
use std::io;
use std::os::unix::fs::MetadataExt;
use std::time::{Duration, Instant};
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
pub struct IdRange {
    pub start: u32,
    pub count: u32,
}
#[path = "production_namespace_audit.rs"]
mod namespace_audit;
fn descriptors() -> io::Result<BTreeMap<i32, (u64, u64, u32)>> {
    let numbers: Vec<i32> = fs::read_dir("/proc/self/fd")?
        .map(|e| {
            e.and_then(|e| {
                e.file_name()
                    .to_string_lossy()
                    .parse()
                    .map_err(|_| io::Error::other("fd number"))
            })
        })
        .collect::<io::Result<_>>()?;
    let mut result = BTreeMap::new();
    for number in numbers {
        match fs::metadata(format!("/proc/self/fd/{number}")) {
            Ok(m) => {
                result.insert(number, (m.dev(), m.ino(), m.mode()));
            }
            Err(e) if e.kind() == io::ErrorKind::NotFound => {}
            Err(e) => return Err(e),
        }
    }
    Ok(result)
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args().collect();
    if args.len() != 5 || args[1] != "observe" {
        return Err("usage: userns-audit observe UID_START GID_START COUNT".into());
    }
    let uids = IdRange {
        start: args[2].parse()?,
        count: args[4].parse()?,
    };
    let gids = IdRange {
        start: args[3].parse()?,
        count: uids.count,
    };
    let before = descriptors()?;
    let started = Instant::now();
    let result = namespace_audit::audit_existing_user_namespaces(
        uids,
        gids,
        Instant::now() + Duration::from_secs(40),
    );
    let report = match &result {
        Ok(guard) => guard.report().clone(),
        Err(error) => error.report().clone(),
    };
    let status = report.status;
    drop(result);
    let after = descriptors()?;
    if before != after {
        return Err("owned descriptor retirement mismatch".into());
    }
    println!(
        "{}",
        serde_json::to_string(&serde_json::json!({
            "schema":"pocket4-userns-audit-observation-v1",
            "report":report,
            "elapsed_ms":started.elapsed().as_millis(),
            "requested_uids":uids,"requested_gids":gids,
            "namespace_mapping_authorized":false,
            "owned_descriptor_set_restored":true,
            "status":status
        }))?
    );
    Ok(())
}
