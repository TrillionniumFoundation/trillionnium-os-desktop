//! Strict Debian control/dependency checks for a pinned systemd package family.
//! Binary package dependencies have no build profiles or architecture filters.
use crate::{Result, ensure};
use std::{cmp::Ordering, collections::BTreeMap};

pub(crate) type Fields = BTreeMap<String, String>;

pub(crate) fn control(text: &str) -> Result<Vec<Fields>> {
    ensure(
        text.len() <= 32 * 1024 * 1024 && !text.contains('\0') && !text.contains('\r'),
        "Debian control input exceeds bounds or contains unsupported bytes",
    )?;
    let mut result = Vec::new();
    let mut fields = Fields::new();
    let mut previous: Option<String> = None;
    for line in text.lines().chain([""]) {
        if line.is_empty() {
            if !fields.is_empty() {
                result.push(std::mem::take(&mut fields));
            }
            previous = None;
        } else if line.starts_with([' ', '\t']) {
            let key = previous
                .as_ref()
                .ok_or("orphan Debian control continuation")?;
            let value = fields
                .get_mut(key)
                .ok_or("missing preceding control field")?;
            value.push('\n');
            value.push_str(line);
        } else {
            let (key, value) = line
                .split_once(':')
                .ok_or("malformed Debian control field")?;
            ensure(
                !key.is_empty() && key.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-'),
                "invalid Debian control field name",
            )?;
            ensure(
                fields
                    .insert(key.into(), value.trim_start().into())
                    .is_none(),
                "repeated Debian control field",
            )?;
            previous = Some(key.into());
        }
    }
    ensure(
        !result.is_empty() && result.len() <= 32768,
        "Debian control stanza count differs",
    )?;
    Ok(result)
}

pub(crate) fn field<'a>(fields: &'a Fields, key: &str) -> Result<&'a str> {
    let value = fields
        .get(key)
        .ok_or_else(|| format!("missing Debian field: {key}"))?;
    ensure(
        !value.is_empty() && !value.contains('\n'),
        "missing or folded scalar Debian field",
    )?;
    Ok(value)
}

fn package_name(name: &str) -> bool {
    !name.is_empty()
        && name
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b"+.-".contains(&b))
}

fn version_parts(version: &str) -> Result<(u64, &str, &str)> {
    ensure(
        !version.is_empty()
            && version
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b".+:~-".contains(&b)),
        "invalid Debian version",
    )?;
    let (epoch, rest) = if let Some((epoch, rest)) = version.split_once(':') {
        ensure(
            !epoch.is_empty() && epoch.bytes().all(|b| b.is_ascii_digit()),
            "invalid Debian epoch",
        )?;
        (epoch.parse()?, rest)
    } else {
        (0, version)
    };
    let (upstream, revision) = rest.rsplit_once('-').unwrap_or((rest, "0"));
    ensure(
        upstream.as_bytes().first().is_some_and(u8::is_ascii_digit) && !revision.is_empty(),
        "invalid Debian upstream/revision",
    )?;
    Ok((epoch, upstream, revision))
}

fn order(byte: Option<u8>) -> i32 {
    match byte {
        Some(b'~') => -1,
        None => 0,
        Some(b) if b.is_ascii_alphabetic() => i32::from(b),
        Some(b) => i32::from(b) + 256,
    }
}

fn revision_cmp(mut a: &[u8], mut b: &[u8]) -> Ordering {
    while !a.is_empty() || !b.is_empty() {
        while a.first().is_some_and(|b| !b.is_ascii_digit())
            || b.first().is_some_and(|b| !b.is_ascii_digit())
        {
            // A digit terminates the nonnumeric part, exactly like end of string.
            let av = a.first().copied().filter(|b| !b.is_ascii_digit());
            let bv = b.first().copied().filter(|b| !b.is_ascii_digit());
            let compared = order(av).cmp(&order(bv));
            if compared != Ordering::Equal {
                return compared;
            }
            if av.is_some() {
                a = &a[1..];
            }
            if bv.is_some() {
                b = &b[1..];
            }
        }
        while a.first() == Some(&b'0') {
            a = &a[1..];
        }
        while b.first() == Some(&b'0') {
            b = &b[1..];
        }
        let an = a.iter().take_while(|b| b.is_ascii_digit()).count();
        let bn = b.iter().take_while(|b| b.is_ascii_digit()).count();
        let compared = an.cmp(&bn).then_with(|| a[..an].cmp(&b[..bn]));
        if compared != Ordering::Equal {
            return compared;
        }
        a = &a[an..];
        b = &b[bn..];
    }
    Ordering::Equal
}

pub(super) fn version_cmp(a: &str, b: &str) -> Result<Ordering> {
    let (ae, au, ar) = version_parts(a)?;
    let (be, bu, br) = version_parts(b)?;
    Ok(ae
        .cmp(&be)
        .then_with(|| revision_cmp(au.as_bytes(), bu.as_bytes()))
        .then_with(|| revision_cmp(ar.as_bytes(), br.as_bytes())))
}

#[derive(Clone, Debug)]
struct Relation {
    name: String,
    architecture: Option<String>,
    constraint: Option<(String, String)>,
}

fn relation(text: &str) -> Result<Relation> {
    let text = text.trim();
    let (name, constraint) = if let Some((name, relation)) = text.split_once('(') {
        let relation = relation
            .strip_suffix(')')
            .ok_or("unclosed Debian version constraint")?;
        let terms: Vec<_> = relation.split_whitespace().collect();
        ensure(
            terms.len() == 2 && ["<<", "<=", "=", ">=", ">>"].contains(&terms[0]),
            "unsupported Debian version constraint",
        )?;
        version_parts(terms[1])?;
        (name.trim(), Some((terms[0].into(), terms[1].into())))
    } else {
        (text, None)
    };
    let (name, architecture) = match name.split_once(':') {
        Some((name, architecture)) => {
            ensure(
                ["any", "native", "amd64", "all"].contains(&architecture),
                "unsupported dependency architecture",
            )?;
            (name, Some(architecture.into()))
        }
        None => (name, None),
    };
    ensure(package_name(name), "invalid dependency package name")?;
    Ok(Relation {
        name: name.into(),
        architecture,
        constraint,
    })
}

fn accepts(constraint: &Option<(String, String)>, provided: Option<&str>) -> Result<bool> {
    let Some((operator, want)) = constraint else {
        return Ok(true);
    };
    let Some(provided) = provided else {
        return Ok(false);
    };
    let cmp = version_cmp(provided, want)?;
    Ok(match operator.as_str() {
        "<<" => cmp == Ordering::Less,
        "<=" => cmp != Ordering::Greater,
        "=" => cmp == Ordering::Equal,
        ">=" => cmp != Ordering::Less,
        ">>" => cmp == Ordering::Greater,
        _ => return Err("unsupported version operator".into()),
    })
}

fn satisfies(want: &Relation, package: &Fields) -> Result<bool> {
    let arch = field(package, "Architecture")?;
    if !["amd64", "all"].contains(&arch) {
        return Ok(false);
    }
    if let Some(requested) = &want.architecture {
        if requested != "any" && requested != "native" && requested != arch && arch != "all" {
            return Ok(false);
        }
        if requested == "any"
            && !matches!(
                package.get("Multi-Arch").map(String::as_str),
                Some("allowed" | "foreign")
            )
        {
            return Ok(false);
        }
    }
    if field(package, "Package")? == want.name {
        return accepts(&want.constraint, Some(field(package, "Version")?));
    }
    for provided in package
        .get("Provides")
        .into_iter()
        .flat_map(|p| p.split(','))
    {
        let provided = relation(provided)?;
        ensure(
            provided.architecture.is_none()
                && provided.constraint.as_ref().is_none_or(|(op, _)| op == "="),
            "invalid Debian Provides relation",
        )?;
        if provided.name == want.name {
            return accepts(
                &want.constraint,
                provided
                    .constraint
                    .as_ref()
                    .map(|(_, version)| version.as_str()),
            );
        }
    }
    Ok(false)
}

/// Evaluate actual package metadata, not a supplied `dependencies_satisfied` flag.
pub(crate) fn closure(installed: &[Fields], candidates: &[Fields]) -> Result<Vec<String>> {
    let mut state = BTreeMap::<(String, String), Fields>::new();
    for package in installed
        .iter()
        .filter(|p| p.get("Status").is_some_and(|s| s == "install ok installed"))
    {
        let key = (
            field(package, "Package")?.into(),
            field(package, "Architecture")?.into(),
        );
        ensure(
            state.insert(key, package.clone()).is_none(),
            "duplicate installed package identity",
        )?;
    }
    for candidate in candidates {
        let key = (
            field(candidate, "Package")?.into(),
            field(candidate, "Architecture")?.into(),
        );
        ensure(
            state.contains_key(&key),
            "candidate is outside the installed package family",
        )?;
        state.insert(key, candidate.clone());
    }
    let mut verified = Vec::new();
    // Recheck the complete installed state after replacement, including reverse
    // dependencies from packages outside the systemd source family.
    for package in state.values() {
        for name in ["Pre-Depends", "Depends"] {
            for requirement in package.get(name).into_iter().flat_map(|v| v.split(',')) {
                let mut found = false;
                for alternative in requirement.split('|') {
                    let alternative = relation(alternative)?;
                    for available in state.values() {
                        if satisfies(&alternative, available)? {
                            found = true;
                            break;
                        }
                    }
                    if found {
                        break;
                    }
                }
                ensure(
                    found,
                    &format!(
                        "unsatisfied systemd candidate {name}: {} -> {requirement}",
                        field(package, "Package")?
                    ),
                )?;
                verified.push(format!(
                    "{} {name}: {}",
                    field(package, "Package")?,
                    requirement.trim()
                ));
            }
        }
        for name in ["Breaks", "Conflicts"] {
            for requirement in package.get(name).into_iter().flat_map(|v| v.split(',')) {
                let relation = relation(requirement)?;
                for other in state.values() {
                    if field(other, "Package")? == field(package, "Package")? {
                        continue;
                    }
                    ensure(
                        !satisfies(&relation, other)?,
                        &format!("systemd candidate {name} installed package: {requirement}"),
                    )?;
                }
            }
        }
    }
    Ok(verified)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn debian_versions_handle_epochs_tildes_digits_and_revisions() -> Result<()> {
        for (a, b, expected) in [
            ("1.0", "1.0-0", Ordering::Equal),
            ("1:1", "2.0", Ordering::Greater),
            (
                "259.9-0ubuntu0.1+p4gentmp2",
                "259.9-0ubuntu0.1",
                Ordering::Greater,
            ),
            ("1.2~rc1", "1.2", Ordering::Less),
            ("1.02", "1.2", Ordering::Equal),
            ("1.9", "1.10", Ordering::Less),
            ("1.0a", "1.0+", Ordering::Less),
            ("1.0~~", "1.0~", Ordering::Less),
            ("1.0a1", "1.0a01", Ordering::Equal),
        ] {
            assert_eq!(version_cmp(a, b)?, expected, "{a} vs {b}");
            assert_eq!(version_cmp(b, a)?, expected.reverse());
        }
        assert!(version_cmp("x", "1").is_err());
        Ok(())
    }
    fn one(text: &str) -> Fields {
        control(text).unwrap().remove(0)
    }
    #[test]
    fn complete_family_versions_and_external_alternatives_are_evaluated() -> Result<()> {
        let mut installed = vec![
            one(
                "Package: systemd\nArchitecture: amd64\nVersion: 259.9-0ubuntu0.1\nStatus: install ok installed\n",
            ),
            one(
                "Package: libsystemd-shared\nArchitecture: amd64\nVersion: 259.9-0ubuntu0.1\nStatus: install ok installed\n",
            ),
            one(
                "Package: libc6\nArchitecture: amd64\nVersion: 2.42-1ubuntu1\nStatus: install ok installed\n",
            ),
        ];
        let pid1 = one(
            "Package: systemd\nArchitecture: amd64\nVersion: 259.9-0ubuntu0.1+p4gentmp2\nDepends: libsystemd-shared (= 259.9-0ubuntu0.1+p4gentmp2), missing | libc6 (>= 2.42)\n",
        );
        assert!(closure(&installed, std::slice::from_ref(&pid1)).is_err());
        let shared = one(
            "Package: libsystemd-shared\nArchitecture: amd64\nVersion: 259.9-0ubuntu0.1+p4gentmp2\n",
        );
        assert_eq!(
            closure(&installed, &[pid1.clone(), shared.clone()])?.len(),
            2
        );
        installed[2].insert("Version".into(), "2.41".into());
        assert!(closure(&installed, &[pid1, shared]).is_err());
        Ok(())
    }
    #[test]
    fn duplicate_controls_and_unversioned_provides_do_not_bypass_constraints() -> Result<()> {
        assert!(control("Package: a\nPackage: b\n").is_err());
        let package =
            one("Package: provider\nVersion: 1\nArchitecture: amd64\nProvides: libexample\n");
        assert!(!satisfies(&relation("libexample (>= 1)")?, &package)?);
        assert!(satisfies(&relation("libexample")?, &package)?);
        assert!(relation("package [!amd64]").is_err());
        assert!(relation("package (>= 1) trailing").is_err());
        Ok(())
    }
}
