//! The two normal Java catalog operations, bound to the selected four-image cohort.
//! The public request selects neither a classpath nor a JAR digest. The digest is
//! read from the original root-sealed base manifest and checked against the whole
//! readonly normal system_ext JAR before and after the factory-owned operation.
use super::*;
use crate::production_selection::early_generation::EarlyApplicationAuthority;
use std::time::Instant;

pub(super) const OUTPUT_BYTES: usize = 2 * 1024 * 1024;
const CLASS: &str = "com.android.droidloom.catalog.ApplicationCatalog";
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(tag = "catalog", deny_unknown_fields)]
pub(crate) enum CatalogCommand {
    List {
        user: u32,
    },
    Icon {
        user: u32,
        component: String,
        size: u32,
    },
}
impl CatalogCommand {
    pub(super) fn validate(&self) -> Result<()> {
        let user = match self {
            Self::List { user } | Self::Icon { user, .. } => *user,
        };
        require(
            user <= 21_474,
            "catalog user exceeds the owned Android mapping",
        )?;
        if let Self::Icon {
            component, size, ..
        } = self
        {
            require(
                (16..=512).contains(size),
                "catalog icon extent is outside the fixed bound",
            )?;
            require(
                component.len() <= 511
                    && component
                        .split_once('/')
                        .is_some_and(|(package, activity)| {
                            package_valid(package)
                                && !activity.is_empty()
                                && activity.bytes().all(|b| {
                                    b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_' | b'$')
                                })
                        }),
                "catalog icon component is not an exact bounded launcher identity",
            )?;
        }
        Ok(())
    }
    fn arguments(&self) -> Result<Vec<CString>> {
        self.validate()?;
        let mut values = vec![
            "/system/bin/app_process64".to_owned(),
            "-Xint".to_owned(),
            "-Xusejit:false".to_owned(),
            "/system/bin".to_owned(),
            CLASS.to_owned(),
        ];
        // These readonly Java roles must not acquire appdomain/JIT permissions.
        match self {
            Self::List { user } => {
                values.extend(["list".into(), "--user".into(), user.to_string()])
            }
            Self::Icon {
                user,
                component,
                size,
            } => values.extend([
                "icon".into(),
                "--user".into(),
                user.to_string(),
                "--component".into(),
                component.clone(),
                "--size".into(),
                size.to_string(),
            ]),
        }
        values
            .into_iter()
            .map(|value| CString::new(value).map_err(external))
            .collect()
    }
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct CatalogRequest {
    command: CatalogCommand,
    selected_jar_sha256: String,
}
impl CatalogRequest {
    pub(super) fn validate(&self) -> Result<()> {
        self.command.validate()?;
        require(
            digest_valid(&self.selected_jar_sha256),
            "catalog JAR is not a selected complete digest",
        )
    }
    pub(super) fn arguments(&self) -> Result<Vec<CString>> {
        self.validate()?;
        self.command.arguments()
    }
    pub(super) fn jar_digest(&self) -> &str {
        &self.selected_jar_sha256
    }
}
fn digest_valid(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

pub(crate) fn catalog_early(
    authority: &EarlyApplicationAuthority<'_>,
    command: CatalogCommand,
    overall_deadline: Instant,
) -> Result<String> {
    let deadline = (Instant::now() + QUERY_LIMIT).min(overall_deadline);
    command.validate()?;
    authority.ready().map_err(external)?;
    let framework = authority.observe_framework().map_err(external)?;
    let epoch = authority.epoch(&framework).map_err(external)?;
    let digest = authority.catalog_jar_digest().map_err(external)?;
    let request = CatalogRequest {
        command,
        selected_jar_sha256: digest,
    };
    request.validate()?;
    let files = authority.descriptors(c"app_process64").map_err(external)?;
    require(
        files.len() == 12,
        "catalog did not borrow the fixed original descriptor prefix",
    )?;
    let (uid, gid) = authority.mapped_root().map_err(external)?;
    let jar =
        worker::executable::bind_catalog(&files[2], request.jar_digest(), uid, gid, deadline)?;
    let operation = ApplicationOperation::Catalog {
        value: request.clone(),
    };
    let result = factory_query::run(authority, &operation, deadline);
    let result = workflow::finish_effect(
        result,
        || {
            authority.ready().map_err(external)?;
            jar.revalidate(&files[2], request.jar_digest(), uid, gid, deadline)?;
            require(
                authority.catalog_jar_digest().map_err(external)? == request.selected_jar_sha256,
                "catalog selected cohort changed",
            )?;
            require(
                authority.epoch(&framework).map_err(external)? == epoch,
                "catalog framework epoch changed",
            )
        },
        deadline,
    )?;
    require(
        result.output.status.success() && result.receipt.successful_retirement(),
        "catalog process did not complete and retire normally",
    )?;
    let output = String::from_utf8(result.output.stdout).map_err(external)?;
    let output = output.trim_end_matches(['\r', '\n']).to_owned();
    require(
        !output.is_empty() && output.len() <= OUTPUT_BYTES,
        "catalog output has an invalid size",
    )?;
    if let CatalogCommand::Icon { size, .. } = &request.command {
        validate_icon(&output, *size)?;
    }
    eprintln!("droidloom-application-catalog {}",serde_json::to_string(
        &serde_json::json!({"operation":request.command,"selected_jar_sha256":request.selected_jar_sha256,
            "receipt":result.receipt,"application_acceptance":false})
    ).map_err(external)?);
    Ok(output)
}

fn base64_digit(byte: u8) -> Result<u8> {
    match byte {
        b'A'..=b'Z' => Ok(byte - b'A'),
        b'a'..=b'z' => Ok(byte - b'a' + 26),
        b'0'..=b'9' => Ok(byte - b'0' + 52),
        b'+' => Ok(62),
        b'/' => Ok(63),
        _ => Err(reject("icon has a non-base64 character")),
    }
}
fn decode_icon(value: &str) -> Result<Vec<u8>> {
    require(
        !value.is_empty() && value.len() <= OUTPUT_BYTES && value.len() % 4 == 0,
        "icon base64 length is not bounded and canonical",
    )?;
    let mut output = Vec::with_capacity(value.len() / 4 * 3);
    let total = value.len() / 4;
    for (index, block) in value.as_bytes().chunks_exact(4).enumerate() {
        let a = base64_digit(block[0])?;
        let b = base64_digit(block[1])?;
        output.push((a << 2) | (b >> 4));
        if block[2] == b'=' {
            require(
                index + 1 == total && block[3] == b'=' && b & 15 == 0,
                "icon base64 two-byte padding is not canonical",
            )?;
        } else {
            let c = base64_digit(block[2])?;
            output.push((b << 4) | (c >> 2));
            if block[3] == b'=' {
                require(
                    index + 1 == total && c & 3 == 0,
                    "icon base64 padding is not canonical",
                )?;
            } else {
                output.push((c << 6) | base64_digit(block[3])?);
            }
        }
    }
    Ok(output)
}
fn validate_icon(value: &str, size: u32) -> Result<()> {
    let bytes = decode_icon(value)?;
    require(
        bytes.starts_with(b"\x89PNG\r\n\x1a\n"),
        "catalog icon is not a PNG",
    )?;
    let mut at = 8usize;
    let mut chunks = 0usize;
    let mut image_data = false;
    while at < bytes.len() {
        require(
            chunks < 4096 && bytes.len() - at >= 12,
            "catalog icon chunk count or size is invalid",
        )?;
        let length = u32::from_be_bytes(bytes[at..at + 4].try_into().unwrap()) as usize;
        let end = at
            .checked_add(12)
            .and_then(|n| n.checked_add(length))
            .ok_or_else(|| reject("catalog PNG chunk length overflow"))?;
        require(end <= bytes.len(), "catalog PNG chunk is truncated")?;
        let kind = &bytes[at + 4..at + 8];
        let payload = &bytes[at + 8..end - 4];
        require(
            kind.iter().all(u8::is_ascii_alphabetic)
                && crc32fast::hash(&bytes[at + 4..end - 4])
                    == u32::from_be_bytes(bytes[end - 4..end].try_into().unwrap()),
            "catalog PNG chunk identity or checksum differs",
        )?;
        if chunks == 0 {
            require(
                kind == b"IHDR"
                    && payload.len() == 13
                    && u32::from_be_bytes(payload[0..4].try_into().unwrap()) == size
                    && u32::from_be_bytes(payload[4..8].try_into().unwrap()) == size,
                "catalog PNG extent differs from the requested icon",
            )?;
        } else {
            require(kind != b"IHDR", "catalog PNG repeats its image header")?;
        }
        if kind == b"IDAT" {
            image_data = true;
        }
        if kind == b"IEND" {
            return require(
                payload.is_empty() && end == bytes.len() && image_data,
                "catalog PNG does not have one complete image ending",
            );
        }
        at = end;
        chunks += 1;
    }
    Err(reject("catalog PNG has no complete ending"))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn catalog_commands_have_only_two_interpreted_fixed_class_shapes() {
        for command in [
            CatalogCommand::List { user: 0 },
            CatalogCommand::Icon {
                user: 0,
                component: "org.mozilla.firefox/org.mozilla.firefox.App".into(),
                size: 128,
            },
        ] {
            let argv = command
                .arguments()
                .unwrap()
                .into_iter()
                .map(|s| s.into_string().unwrap())
                .collect::<Vec<_>>();
            assert_eq!(
                &argv[..5],
                &[
                    "/system/bin/app_process64",
                    "-Xint",
                    "-Xusejit:false",
                    "/system/bin",
                    CLASS
                ]
            );
            assert!(ApplicationRead::from_command(&argv).is_err());
            let request = ApplicationOperation::Catalog {
                value: CatalogRequest {
                    command,
                    selected_jar_sha256: "a".repeat(64),
                },
            };
            assert_eq!(request.domain(), OperationDomain::CatalogRead);
            assert_eq!(request.binary(), c"app_process64");
            assert!(request.uses_app_process());
            assert!(!request.needs_content_jar());
            assert_eq!(request.descriptor_count(), 15);
            assert_eq!(request.output_limit(), OUTPUT_BYTES);
            assert!(
                request.environment(QueryProjection::EarlyDev).contains(
                    &c"CLASSPATH=/system/system_ext/framework/droidloom-input-bridge.jar"
                )
            );
        }
        for command in [
            CatalogCommand::List { user: 21_475 },
            CatalogCommand::Icon {
                user: 0,
                component: "org.mozilla.firefox/../arbitrary".into(),
                size: 16,
            },
            CatalogCommand::Icon {
                user: 0,
                component: "org.mozilla.firefox/.App".into(),
                size: 513,
            },
        ] {
            assert!(command.arguments().is_err());
        }
        for message in [
            r#"{"catalog":"List","user":0,"classpath":"/data/arbitrary.jar"}"#,
            r#"{"catalog":"Icon","user":0,"component":"org.mozilla.firefox/.App","size":16,"class":"Another"}"#,
            r#"{"catalog":"Exec","user":0}"#,
        ] {
            assert!(serde_json::from_str::<CatalogCommand>(message).is_err());
        }
        let read = ApplicationOperation::Read {
            value: ApplicationRead::PackagePaths {
                package: "org.mozilla.firefox".into(),
                user: 0,
            },
        };
        assert_eq!(read.output_limit(), OUTPUT_LIMIT);
        assert!(read.catalog_jar_digest().is_none());
    }
    #[test]
    fn catalog_icon_rejects_wrong_extent_checksum_trailing_records_and_noncanonical_base64() {
        let valid = "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAEklEQVR4nGNgGAWjYBSMAggAAAQQAAFVN1rQAAAAAElFTkSuQmCC";
        validate_icon(valid, 16).unwrap();
        assert!(validate_icon(valid, 32).is_err());
        for invalid in ["not a PNG", "A===", "====", "AB==", "AA=A", "AA==AA=="] {
            assert!(validate_icon(invalid, 16).is_err());
        }
        let mut corrupt = valid.as_bytes().to_vec();
        corrupt[64] = if corrupt[64] == b'A' { b'B' } else { b'A' };
        assert!(validate_icon(std::str::from_utf8(&corrupt).unwrap(), 16).is_err());
        let longer = format!("{valid}AAAA");
        assert!(validate_icon(&longer, 16).is_err());
    }
}
