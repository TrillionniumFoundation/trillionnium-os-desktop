//! Actual preimage and committed source-pair custody for one initial H2 lease.
//! All paths are derived from the fixed CURRENT or its bounded typed source
//! manifest. No caller success value can construct the retained publication.
use super::source::*;
use serde::{
    Deserialize, Deserializer,
    de::{self, MapAccess, SeqAccess, Visitor},
};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{
    fmt,
    fs::{self, File, OpenOptions},
    os::{
        fd::AsRawFd,
        unix::fs::{FileExt, MetadataExt, OpenOptionsExt},
    },
    path::{Path, PathBuf},
};
pub(super) const CURRENT: &str = "/home/alex/work/pocket4-android-final/CONTINUATION_CURRENT.json";
const ROOT: &str = "/etc/droidloom/native-application-leaves";
fn hash(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}
pub(super) fn f9(m: &fs::Metadata) -> Result<[u64; 9], String> {
    let ns = |s: i64, n: i64| {
        u64::try_from(i128::from(s) * 1_000_000_000 + i128::from(n))
            .map_err(|_| "negative source file timestamp".to_owned())
    };
    Ok([
        m.dev(),
        m.ino(),
        u64::from(m.mode()),
        u64::from(m.uid()),
        u64::from(m.gid()),
        m.nlink(),
        m.len(),
        ns(m.mtime(), m.mtime_nsec())?,
        ns(m.ctime(), m.ctime_nsec())?,
    ])
}
fn body(file: &File, size: u64) -> Result<Vec<u8>, String> {
    let mut out = vec![0; usize::try_from(size).map_err(|e| e.to_string())?];
    file.read_exact_at(&mut out, 0).map_err(|e| e.to_string())?;
    require(
        file.read_at(&mut [0; 1], size).map_err(|e| e.to_string())? == 0,
        "source input grew",
    )?;
    Ok(out)
}
struct Unique(Value);
impl<'de> Deserialize<'de> for Unique {
    fn deserialize<D: Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        struct V;
        impl<'de> Visitor<'de> for V {
            type Value = Unique;
            fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
                f.write_str("finite JSON with unique object keys")
            }
            fn visit_bool<E: de::Error>(self, v: bool) -> Result<Unique, E> {
                Ok(Unique(Value::Bool(v)))
            }
            fn visit_u64<E: de::Error>(self, v: u64) -> Result<Unique, E> {
                Ok(Unique(Value::Number(v.into())))
            }
            fn visit_i64<E: de::Error>(self, v: i64) -> Result<Unique, E> {
                Ok(Unique(Value::Number(v.into())))
            }
            fn visit_f64<E: de::Error>(self, v: f64) -> Result<Unique, E> {
                serde_json::Number::from_f64(v)
                    .map(|v| Unique(Value::Number(v)))
                    .ok_or_else(|| E::custom("nonfinite source number"))
            }
            fn visit_str<E: de::Error>(self, v: &str) -> Result<Unique, E> {
                Ok(Unique(Value::String(v.into())))
            }
            fn visit_string<E: de::Error>(self, v: String) -> Result<Unique, E> {
                Ok(Unique(Value::String(v)))
            }
            fn visit_none<E: de::Error>(self) -> Result<Unique, E> {
                Ok(Unique(Value::Null))
            }
            fn visit_unit<E: de::Error>(self) -> Result<Unique, E> {
                Ok(Unique(Value::Null))
            }
            fn visit_seq<A: SeqAccess<'de>>(self, mut s: A) -> Result<Unique, A::Error> {
                let mut a = Vec::new();
                while let Some(Unique(v)) = s.next_element()? {
                    a.push(v)
                }
                Ok(Unique(Value::Array(a)))
            }
            fn visit_map<A: MapAccess<'de>>(self, mut m: A) -> Result<Unique, A::Error> {
                let mut a = serde_json::Map::new();
                while let Some(k) = m.next_key::<String>()? {
                    if a.contains_key(&k) {
                        return Err(de::Error::custom("duplicate source key"));
                    }
                    let Unique(v) = m.next_value()?;
                    a.insert(k, v);
                }
                Ok(Unique(Value::Object(a)))
            }
        }
        d.deserialize_any(V)
    }
}
fn json(raw: &[u8]) -> Result<Value, String> {
    serde_json::from_slice::<Unique>(raw)
        .map(|v| v.0)
        .map_err(|e| e.to_string())
}
struct Parent {
    path: PathBuf,
    file: File,
    pin: [u64; 5],
}
#[derive(Clone, Copy)]
enum Rule {
    Current,
    Protected,
    Source,
}
fn parent_allowed(pin: &[u64; 5], rule: Rule) -> bool {
    pin[2] & 0o170000 == 0o040000
        && pin[2] & 0o022 == 0
        && match rule {
            Rule::Current => pin[3..5] == [0, 0] || pin[3..5] == [1000, 1000],
            Rule::Protected | Rule::Source => pin[3..5] == [0, 0],
        }
}
struct Held {
    path: PathBuf,
    file: File,
    pin: [u64; 9],
    raw: Vec<u8>,
    parents: Vec<Parent>,
}
impl Held {
    fn open(path: &Path, maximum: u64, rule: Rule) -> Result<Self, String> {
        require(
            path.to_str().is_some_and(|v| {
                v.starts_with('/')
                    && !v.contains('\0')
                    && v[1..]
                        .split('/')
                        .all(|p| !p.is_empty() && p != "." && p != "..")
            }),
            "canonical source publication path required",
        )?;
        let flags = libc::O_NOFOLLOW | libc::O_NONBLOCK | libc::O_CLOEXEC;
        let mut directories = Vec::new();
        let root = OpenOptions::new()
            .read(true)
            .custom_flags(flags | libc::O_DIRECTORY)
            .open("/")
            .map_err(|e| e.to_string())?;
        let id: [u64; 5] = f9(&root.metadata().map_err(|e| e.to_string())?)?[..5]
            .try_into()
            .map_err(|_| "source root identity")?;
        directories.push(Parent {
            path: "/".into(),
            file: root,
            pin: id,
        });
        let parent = path.parent().ok_or("source parent absent")?;
        let mut p = PathBuf::from("/");
        for part in parent.components().skip(1) {
            let std::path::Component::Normal(part) = part else {
                return Err("source parent is not canonical".into());
            };
            let anchor = PathBuf::from(format!(
                "/proc/self/fd/{}",
                directories.last().unwrap().file.as_raw_fd()
            ))
            .join(part);
            p.push(part);
            let file = OpenOptions::new()
                .read(true)
                .custom_flags(flags | libc::O_DIRECTORY)
                .open(anchor)
                .map_err(|e| e.to_string())?;
            let pin: [u64; 5] = f9(&file.metadata().map_err(|e| e.to_string())?)?[..5]
                .try_into()
                .map_err(|_| "source parent identity")?;
            require(
                f9(&fs::symlink_metadata(&p).map_err(|e| e.to_string())?)?[..5] == pin,
                "source parent name differs",
            )?;
            directories.push(Parent {
                path: p.clone(),
                file,
                pin,
            });
        }
        for d in &directories {
            require(
                d.pin[2] & 0o170000 == 0o040000,
                "ordinary source directory required",
            )?;
            require(
                parent_allowed(&d.pin, rule),
                "source parent must retain its exact root/user owner and forbid group/other writes",
            )?;
        }
        let anchor = PathBuf::from(format!(
            "/proc/self/fd/{}",
            directories.last().unwrap().file.as_raw_fd()
        ))
        .join(path.file_name().ok_or("source leaf absent")?);
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(flags)
            .open(anchor)
            .map_err(|e| e.to_string())?;
        let pin = f9(&file.metadata().map_err(|e| e.to_string())?)?;
        require(
            pin[2] & 0o170000 == 0o100000 && pin[5] == 1 && pin[6] > 0 && pin[6] <= maximum,
            "bounded single-link source body required",
        )?;
        match rule {
            Rule::Current => require(
                pin[2..6] == [0o100600, 1000, 1000, 1],
                "actual original CURRENT owner/mode differs",
            )?,
            Rule::Protected => require(
                pin[2..6] == [0o100400, 0, 0, 1],
                "private root source publication differs",
            )?,
            Rule::Source => require(
                pin[3..6] == [0, 0, 1] && pin[2] & 0o222 == 0,
                "immutable normal source publication differs",
            )?,
        }
        let raw = body(&file, pin[6])?;
        let value = Self {
            path: path.into(),
            file,
            pin,
            raw,
            parents: directories,
        };
        value.guard()?;
        Ok(value)
    }
    fn guard(&self) -> Result<(), String> {
        for d in &self.parents {
            require(
                f9(&d.file.metadata().map_err(|e| e.to_string())?)?[..5] == d.pin
                    && f9(&fs::symlink_metadata(&d.path).map_err(|e| e.to_string())?)?[..5]
                        == d.pin,
                "source publication parent identity changed",
            )?;
        }
        require(
            f9(&self.file.metadata().map_err(|e| e.to_string())?)? == self.pin
                && f9(&fs::symlink_metadata(&self.path).map_err(|e| e.to_string())?)? == self.pin
                && body(&self.file, self.pin[6])? == self.raw
                && f9(&self.file.metadata().map_err(|e| e.to_string())?)? == self.pin
                && f9(&fs::symlink_metadata(&self.path).map_err(|e| e.to_string())?)? == self.pin,
            "source publication held/named full body changed",
        )
    }
    fn reference(&self) -> WorkingSourceFilePin {
        WorkingSourceFilePin {
            path: self.path.clone(),
            bytes: self.pin[6],
            sha256: hash(&self.raw),
        }
    }
}
pub(super) struct CurrentBefore {
    held: Held,
}
impl CurrentBefore {
    pub(super) fn capture() -> Result<Self, String> {
        Ok(Self {
            held: Held::open(Path::new(CURRENT), 2 * 1024 * 1024, Rule::Current)?,
        })
    }
    pub(super) fn guard(&self) -> Result<(), String> {
        self.held.guard()
    }
    pub(super) fn raw(&self) -> &[u8] {
        &self.held.raw
    }
    pub(super) fn reference(&self) -> WorkingCurrentPreimage {
        WorkingCurrentPreimage {
            path: self.held.path.clone(),
            bytes: self.held.pin[6],
            sha256: hash(&self.held.raw),
            f9: self.held.pin,
        }
    }
}

/// Captured only after the exact real CURRENT CAS under the two original
/// exclusive locks. The old inode's expected unlink is recorded as a distinct
/// phase, not mislabeled as an unchanged post-CAS F9.
pub(super) struct Publication {
    previous: CurrentBefore,
    previous_retired: [u64; 9],
    current: Held,
    manifest: Held,
    copy: Held,
    catalog: Held,
    selection: Held,
    parsed: WorkingLeafManifest,
}
fn forward(
    before: &Value,
    after: &Value,
    manifest: &WorkingLeafManifest,
    reference: &WorkingSourceFilePin,
) -> Result<(), String> {
    let mut allowed = before.clone();
    let object = allowed
        .as_object_mut()
        .ok_or("CURRENT preimage must be an object")?;
    object.insert(
        "foreground_owner".into(),
        serde_json::to_value(&manifest.foreground_owner).map_err(|e| e.to_string())?,
    );
    object.insert(
        "application_qualification_preparations".into(),
        serde_json::to_value(&manifest.selection).map_err(|e| e.to_string())?,
    );
    object.insert(
        "native_application_leaf_release".into(),
        serde_json::to_value(reference).map_err(|e| e.to_string())?,
    );
    require(
        &allowed == after,
        "CURRENT is not the exact initial-owner/compiled-selection/source-pair successor",
    )
}
impl Publication {
    pub(super) fn capture(
        previous: CurrentBefore,
        origin: &WorkingSourceOrigin,
    ) -> Result<Self, String> {
        origin.validate()?;
        let current = Held::open(Path::new(CURRENT), 2 * 1024 * 1024, Rule::Current)?;
        require(
            current.pin[..2] != previous.held.pin[..2],
            "initial CURRENT was not atomically published to a new inode",
        )?;
        let value = json(&current.raw)?;
        let reference: WorkingSourceFilePin = serde_json::from_value(
            value
                .get("native_application_leaf_release")
                .ok_or("published CURRENT lacks its native source pair")?
                .clone(),
        )
        .map_err(|e| e.to_string())?;
        reference.validate(65536)?;
        require(
            reference.path == PathBuf::from(format!("{ROOT}/releases/{}.json", reference.sha256)),
            "only the exact content-addressed working manifest is admitted",
        )?;
        let manifest = Held::open(&reference.path, 65536, Rule::Protected)?;
        require(
            manifest.reference() == reference,
            "published manifest whole body differs",
        )?;
        let parsed: WorkingLeafManifest =
            serde_json::from_value(json(&manifest.raw)?).map_err(|e| e.to_string())?;
        parsed.validate()?;
        require(
            parsed.working_owner == *origin && parsed.before_current == previous.reference(),
            "manifest does not retain this actual initial owner and CURRENT preimage",
        )?;
        let copy = Held::open(
            &parsed.before_current_copy.path,
            2 * 1024 * 1024,
            Rule::Protected,
        )?;
        require(
            copy.reference() == parsed.before_current_copy && copy.raw == previous.held.raw,
            "root preimage copy differs from the original held CURRENT bytes",
        )?;
        forward(&json(&previous.held.raw)?, &value, &parsed, &reference)?;
        let catalog = Held::open(&parsed.catalog.path, 65536, Rule::Protected)?;
        let selection = Held::open(&parsed.selection.path, 1024 * 1024, Rule::Source)?;
        require(
            catalog.reference() == parsed.catalog && selection.reference() == parsed.selection,
            "normal source selection/catalog bytes differ",
        )?;
        let retired = f9(&previous.held.file.metadata().map_err(|e| e.to_string())?)?;
        require(
            retired[..5] == previous.held.pin[..5]
                && retired[5] == 0
                && retired[6..8] == previous.held.pin[6..8]
                && retired[8] >= previous.held.pin[8]
                && body(&previous.held.file, retired[6])? == previous.held.raw,
            "original CURRENT descriptor did not undergo only the observed final-name unlink",
        )?;
        let out = Self {
            previous,
            previous_retired: retired,
            current,
            manifest,
            copy,
            catalog,
            selection,
            parsed,
        };
        out.guard()?;
        Ok(out)
    }
    pub(super) fn guard(&self) -> Result<(), String> {
        for f in [
            &self.current,
            &self.manifest,
            &self.copy,
            &self.catalog,
            &self.selection,
        ] {
            f.guard()?
        }
        require(
            f9(&self
                .previous
                .held
                .file
                .metadata()
                .map_err(|e| e.to_string())?)?
                == self.previous_retired
                && body(&self.previous.held.file, self.previous_retired[6])?
                    == self.previous.held.raw
                && f9(&self
                    .previous
                    .held
                    .file
                    .metadata()
                    .map_err(|e| e.to_string())?)?
                    == self.previous_retired,
            "retained original CURRENT inode/body changed after publication",
        )
    }
    pub(super) fn reference(&self) -> WorkingSourceFilePin {
        self.manifest.reference()
    }
    pub(super) fn manifest(&self) -> &WorkingLeafManifest {
        &self.parsed
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn current_parent_owner_does_not_accept_shared_writes_or_foreign_uid() {
        for pin in [[1, 2, 0o040755, 0, 0], [1, 2, 0o040700, 1000, 1000]] {
            assert!(parent_allowed(&pin, Rule::Current));
        }
        for pin in [
            [1, 2, 0o040775, 1000, 1000],
            [1, 2, 0o040707, 1000, 1000],
            [1, 2, 0o040755, 1001, 1000],
            [1, 2, 0o040755, 1000, 1001],
            [1, 2, 0o120755, 1000, 1000],
        ] {
            assert!(!parent_allowed(&pin, Rule::Current));
        }
        assert!(!parent_allowed(
            &[1, 2, 0o040755, 1000, 1000],
            Rule::Protected
        ));
        assert!(!parent_allowed(&[1, 2, 0o040755, 1000, 1000], Rule::Source));
    }
    #[test]
    fn source_json_rejects_duplicate_keys_and_distinguishes_boolean_numbers() {
        for raw in [
            br#"{"x":1,"x":2}"#.as_slice(),
            br#"{"x":{"a":1,"a":1}}"#.as_slice(),
        ] {
            assert!(json(raw).is_err());
        }
        assert_ne!(
            json(br#"{"x":true}"#).unwrap(),
            json(br#"{"x":1}"#).unwrap()
        );
    }
}
