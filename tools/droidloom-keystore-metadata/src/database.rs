use crate::Result;
use rusqlite::{Connection, OpenFlags, TransactionBehavior, config::DbConfig, types::ValueRef};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::path::PathBuf;

// Exact version-2 persistent schema from AOSP system/security@cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb.
// These are the stored table definitions; no schema migration is performed.
pub(crate) const TABLES: &[(&str, &str)] = &[
    (
        "version",
        "CREATE TABLE version (id INTEGER PRIMARY KEY, version INTEGER)",
    ),
    (
        "keyentry",
        "CREATE TABLE keyentry (id INTEGER UNIQUE, key_type INTEGER, domain INTEGER, namespace INTEGER, alias BLOB, state INTEGER, km_uuid BLOB)",
    ),
    (
        "blobentry",
        "CREATE TABLE blobentry (id INTEGER PRIMARY KEY, subcomponent_type INTEGER, keyentryid INTEGER, blob BLOB, state INTEGER DEFAULT 0)",
    ),
    (
        "blobmetadata",
        "CREATE TABLE blobmetadata (id INTEGER PRIMARY KEY, blobentryid INTEGER, tag INTEGER, data ANY, UNIQUE (blobentryid, tag))",
    ),
    (
        "keyparameter",
        "CREATE TABLE keyparameter (keyentryid INTEGER, tag INTEGER, data ANY, security_level INTEGER)",
    ),
    (
        "keymetadata",
        "CREATE TABLE keymetadata (keyentryid INTEGER, tag INTEGER, data ANY, UNIQUE (keyentryid, tag))",
    ),
    (
        "grant",
        "CREATE TABLE grant (id INTEGER UNIQUE, grantee INTEGER, keyentryid INTEGER, access_vector INTEGER)",
    ),
];
pub(crate) const INDEXES: &[(&str, &str)] = &[
    (
        "keyentry_id_index",
        "CREATE INDEX keyentry_id_index ON keyentry(id)",
    ),
    (
        "keyentry_domain_namespace_index",
        "CREATE INDEX keyentry_domain_namespace_index ON keyentry(domain, namespace, alias)",
    ),
    (
        "keyentry_state_index",
        "CREATE INDEX keyentry_state_index ON keyentry(state)",
    ),
    (
        "blobentry_keyentryid_index",
        "CREATE INDEX blobentry_keyentryid_index ON blobentry(keyentryid)",
    ),
    (
        "blobentry_state_index",
        "CREATE INDEX blobentry_state_index ON blobentry(subcomponent_type, state)",
    ),
    (
        "blobmetadata_blobentryid_index",
        "CREATE INDEX blobmetadata_blobentryid_index ON blobmetadata(blobentryid)",
    ),
    (
        "keyparameter_keyentryid_index",
        "CREATE INDEX keyparameter_keyentryid_index ON keyparameter(keyentryid)",
    ),
    (
        "keymetadata_keyentryid_index",
        "CREATE INDEX keymetadata_keyentryid_index ON keymetadata(keyentryid)",
    ),
];
const AUTO_INDEXES: &[&str] = &[
    "sqlite_autoindex_keyentry_1",
    "sqlite_autoindex_blobmetadata_1",
    "sqlite_autoindex_keymetadata_1",
    "sqlite_autoindex_grant_1",
];
pub(crate) const DEFAULT_UUID: &[u8] = &[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1];
pub(crate) fn open(path: PathBuf) -> Result<Connection> {
    let db = Connection::open_with_flags(
        path,
        OpenFlags::SQLITE_OPEN_READ_WRITE
            | OpenFlags::SQLITE_OPEN_NO_MUTEX
            | OpenFlags::SQLITE_OPEN_NOFOLLOW,
    )
    .map_err(|_| "private_database_open_failed")?;
    db.set_db_config(DbConfig::SQLITE_DBCONFIG_DEFENSIVE, true)
        .map_err(|_| "defensive_sqlite_configuration_failed")?;
    db.execute_batch(
        "PRAGMA trusted_schema=OFF; PRAGMA temp_store=MEMORY; PRAGMA synchronous=FULL;",
    )
    .map_err(|_| "private_sqlite_configuration_failed")?;
    Ok(db)
}
fn normalized(sql: &str) -> String {
    sql.chars()
        .filter(|c| !c.is_ascii_whitespace() && *c != ';')
        .flat_map(char::to_lowercase)
        .collect::<String>()
        .replace("createtableifnotexists", "createtable")
        .replace("createindexifnotexists", "createindex")
}
pub(crate) fn validate_schema(db: &Connection) -> Result<()> {
    let mut statement = db
        .prepare("SELECT type, name, sql FROM sqlite_schema ORDER BY name")
        .map_err(|_| "schema_query_failed")?;
    let objects = statement
        .query_map([], |r| {
            Ok((
                r.get::<_, String>(0)?,
                r.get::<_, String>(1)?,
                r.get::<_, Option<String>>(2)?,
            ))
        })
        .map_err(|_| "schema_query_failed")?;
    let mut seen = BTreeSet::new();
    for object in objects {
        let (kind, name, sql) = object.map_err(|_| "schema_decode_failed")?;
        let expected = match kind.as_str() {
            "table" => TABLES.iter().find(|(n, _)| *n == name).map(|(_, s)| *s),
            "index" if AUTO_INDEXES.contains(&name.as_str()) && sql.is_none() => {
                seen.insert(name);
                continue;
            }
            "index" => INDEXES.iter().find(|(n, _)| *n == name).map(|(_, s)| *s),
            _ => return Err("unknown_schema_object_refused"),
        }
        .ok_or("unknown_schema_object_refused")?;
        if sql.as_deref().map(normalized) != Some(normalized(expected)) {
            return Err("schema_definition_mismatch");
        }
        seen.insert(name);
    }
    for name in TABLES
        .iter()
        .chain(INDEXES)
        .map(|(n, _)| *n)
        .chain(AUTO_INDEXES.iter().copied())
    {
        if !seen.contains(name) {
            return Err("required_schema_object_missing");
        }
    }
    let versions: i64 = db.query_row(
        "SELECT count(*) FROM version WHERE typeof(id)='integer' AND id=0 AND typeof(version)='integer' AND version=2",
        [], |r| r.get(0)).map_err(|_| "schema_version_query_failed")?;
    if versions != 1 || count(db, "SELECT count(*) FROM version")? != 1 {
        return Err("unsupported_schema_version");
    }
    integrity(db)
}
fn integrity(db: &Connection) -> Result<()> {
    let mut statement = db
        .prepare("PRAGMA integrity_check")
        .map_err(|_| "integrity_check_failed")?;
    let values: Vec<String> = statement
        .query_map([], |r| r.get(0))
        .map_err(|_| "integrity_check_failed")?
        .collect::<rusqlite::Result<_>>()
        .map_err(|_| "integrity_check_failed")?;
    if values != ["ok"] {
        return Err("database_integrity_failed");
    }
    Ok(())
}
fn count(db: &Connection, sql: &str) -> Result<u64> {
    let value: i64 = db
        .query_row(sql, [], |r| r.get(0))
        .map_err(|_| "aggregate_query_failed")?;
    u64::try_from(value).map_err(|_| "negative_aggregate_count")
}
#[derive(Serialize)]
pub(crate) struct Counts {
    total_key_entries: u64,
    live_client_entries: u64,
    pub(crate) candidate_key_entries: usize,
    pub(crate) candidate_authorization_rows: u64,
    candidate_blobs_with_outer_encryption_metadata: u64,
}
pub(crate) struct Candidates {
    pub(crate) ids: BTreeSet<i64>,
    pub(crate) counts: Counts,
}
pub(crate) fn candidates(db: &Connection) -> Result<Candidates> {
    // UUID is only a routing filter. This query does NOT authenticate a backend or a key.
    // Keep software/keystore rows intact; reject an ambiguous StrongBox/unknown bucket.
    let sql = "SELECT e.id,
        (SELECT count(*) FROM keyparameter p WHERE p.keyentryid=e.id AND p.security_level=1),
        EXISTS(SELECT 1 FROM blobentry b JOIN blobmetadata m ON m.blobentryid=b.id
               WHERE b.keyentryid=e.id AND b.subcomponent_type=0 AND b.state=0 AND m.tag IN (0,1,2,3,5,6))
        FROM keyentry e
        WHERE typeof(e.id)='integer' AND e.key_type=0 AND e.state=1 AND e.domain IN (0,2)
          AND typeof(e.km_uuid)='blob' AND e.km_uuid=?1
          AND EXISTS(SELECT 1 FROM keyparameter p WHERE p.keyentryid=e.id AND p.security_level=1)
          AND NOT EXISTS(SELECT 1 FROM keyparameter p WHERE p.keyentryid=e.id
                         AND (typeof(p.tag)!='integer' OR typeof(p.security_level)!='integer'
                              OR p.security_level NOT IN (0,1,100)))
          AND (SELECT count(*) FROM blobentry b WHERE b.keyentryid=e.id AND b.subcomponent_type=0 AND b.state=0)=1
          AND EXISTS(SELECT 1 FROM blobentry b WHERE b.keyentryid=e.id AND b.subcomponent_type=0 AND b.state=0
                     AND typeof(b.blob)='blob' AND length(b.blob)>0)
          AND NOT EXISTS(SELECT 1 FROM blobentry b JOIN blobmetadata m ON m.blobentryid=b.id
                         WHERE b.keyentryid=e.id AND b.subcomponent_type=0 AND b.state=0 AND m.tag=4
                           AND (typeof(m.data)!='blob' OR m.data!=e.km_uuid))
        ORDER BY e.id LIMIT 100001";
    let mut statement = db.prepare(sql).map_err(|_| "candidate_query_failed")?;
    let rows = statement
        .query_map([DEFAULT_UUID], |r| {
            Ok((
                r.get::<_, i64>(0)?,
                r.get::<_, i64>(1)?,
                r.get::<_, bool>(2)?,
            ))
        })
        .map_err(|_| "candidate_query_failed")?;
    let mut ids = BTreeSet::new();
    let (mut auth_rows, mut wrapped) = (0, 0);
    for row in rows {
        let (id, n, encrypted) = row.map_err(|_| "candidate_decode_failed")?;
        ids.insert(id);
        auth_rows += u64::try_from(n).map_err(|_| "negative_candidate_count")?;
        wrapped += u64::from(encrypted);
    }
    if ids.len() > 100000 {
        return Err("candidate_count_limit");
    }
    let counts = Counts {
        total_key_entries: count(db, "SELECT count(*) FROM keyentry")?,
        live_client_entries: count(
            db,
            "SELECT count(*) FROM keyentry WHERE key_type=0 AND state=1",
        )?,
        candidate_key_entries: ids.len(),
        candidate_authorization_rows: auth_rows,
        candidate_blobs_with_outer_encryption_metadata: wrapped,
    };
    Ok(Candidates { ids, counts })
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub(crate) struct TableFingerprint {
    rows: u64,
    sha256: String,
}
pub(crate) type Fingerprints = BTreeMap<String, TableFingerprint>;
fn hash_value(hash: &mut Sha256, value: ValueRef<'_>) {
    match value {
        ValueRef::Null => hash.update([0]),
        ValueRef::Integer(v) => {
            hash.update([1]);
            hash.update(v.to_be_bytes());
        }
        ValueRef::Real(v) => {
            hash.update([2]);
            hash.update(v.to_bits().to_be_bytes());
        }
        ValueRef::Text(v) => {
            hash.update([3]);
            hash.update((v.len() as u64).to_be_bytes());
            hash.update(v);
        }
        ValueRef::Blob(v) => {
            hash.update([4]);
            hash.update((v.len() as u64).to_be_bytes());
            hash.update(v);
        }
    }
}
pub(crate) fn fingerprints(db: &Connection, normalize: &BTreeSet<i64>) -> Result<Fingerprints> {
    let mut result = BTreeMap::new();
    for table in TABLES.iter().map(|(n, _)| *n).chain(["sqlite_schema"]) {
        // Table names are hard-coded, never read from database content.
        let mut statement = db
            .prepare(&format!("SELECT rowid, * FROM \"{table}\" ORDER BY rowid"))
            .map_err(|_| "fingerprint_query_failed")?;
        let width = statement.column_count();
        let mut rows = statement
            .query([])
            .map_err(|_| "fingerprint_query_failed")?;
        let mut hash = Sha256::new();
        hash.update((width as u64).to_be_bytes());
        let mut count = 0_u64;
        while let Some(row) = rows.next().map_err(|_| "fingerprint_row_failed")? {
            let rewrite = table == "keyparameter"
                && matches!(row.get_ref(1),
                Ok(ValueRef::Integer(id)) if normalize.contains(&id));
            hash.update([0xff]);
            for column in 0..width {
                let value = row
                    .get_ref(column)
                    .map_err(|_| "fingerprint_value_failed")?;
                if rewrite && column == 4 && value == ValueRef::Integer(1) {
                    hash_value(&mut hash, ValueRef::Integer(0));
                } else {
                    hash_value(&mut hash, value);
                }
            }
            count += 1;
        }
        hash.update(count.to_be_bytes());
        result.insert(
            table.to_owned(),
            TableFingerprint {
                rows: count,
                sha256: hex::encode(hash.finalize()),
            },
        );
    }
    Ok(result)
}
pub(crate) fn apply_to_private_copy(
    db: &mut Connection,
    candidates: &Candidates,
    expected: &Fingerprints,
) -> Result<u64> {
    let tx = db
        .transaction_with_behavior(TransactionBehavior::Immediate)
        .map_err(|_| "private_transaction_start_failed")?;
    let mut changed = 0_u64;
    for id in &candidates.ids {
        changed += tx
            .execute(
                "UPDATE keyparameter SET security_level=0 WHERE keyentryid=?1 AND security_level=1",
                [id],
            )
            .map_err(|_| "private_metadata_update_failed")? as u64;
    }
    if changed != candidates.counts.candidate_authorization_rows
        || fingerprints(&tx, &BTreeSet::new())? != *expected
    {
        return Err("logical_invariant_mismatch_rolled_back");
    }
    integrity(&tx)?;
    tx.commit()
        .map_err(|_| "private_transaction_commit_failed")?;
    Ok(changed)
}
