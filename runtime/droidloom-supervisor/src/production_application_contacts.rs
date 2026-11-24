//! Owned Contacts provider reads and exact fixture identity checks.
//!
//! This is the first native dependency of ContactsSearch. It does not create,
//! edit, search through the UI, or delete a contact, and does not issue an app
//! acceptance or a mutation permit. Every provider operation is executed by
//! the same Ready owner and the fixed app_process64/content.jar input roles.
use super::*;
use std::collections::BTreeSet;
use std::time::{Duration, Instant};

const NAME: &str = "Pocket4 Search QA r12 f4a76c9d";
const EDITED: &str = "Pocket4 Search QA r12 f4a76c9d Edited";
const NAME_MIME: &str = "vnd.android.cursor.item/name";
const RAW_COLUMNS: &[&str] = &["_id", "contact_id", "deleted"];
const NAME_COLUMNS: &[&str] = &["_id", "raw_contact_id", "contact_id", "mimetype", "data1"];
const ACCOUNT_COLUMNS: &[&str] = &[
    "_id",
    "contact_id",
    "account_name",
    "account_type",
    "data_set",
    "deleted",
];
const MAX_ROWS: usize = 256;
const WORK_LIMIT: Duration = Duration::from_secs(240);

#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
#[serde(tag = "contacts_read")]
pub(crate) enum ContactsQuery {
    RawRows,
    FixtureNames,
    OwnedAccount { raw_contact_id: String },
}
impl<'de> Deserialize<'de> for ContactsQuery {
    fn deserialize<D>(deserializer: D) -> std::result::Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        // Internally tagged unit variants otherwise discard extra fields even
        // with deny_unknown_fields. Empty struct variants enforce the complete
        // wire shape while preserving the existing query API and encoding.
        #[derive(Deserialize)]
        #[serde(tag = "contacts_read", deny_unknown_fields)]
        enum StrictQuery {
            RawRows {},
            FixtureNames {},
            OwnedAccount { raw_contact_id: String },
        }
        Ok(match StrictQuery::deserialize(deserializer)? {
            StrictQuery::RawRows {} => Self::RawRows,
            StrictQuery::FixtureNames {} => Self::FixtureNames,
            StrictQuery::OwnedAccount { raw_contact_id } => Self::OwnedAccount { raw_contact_id },
        })
    }
}
fn positive_id(text: &str) -> bool {
    !text.is_empty()
        && text.len() <= 19
        && text.as_bytes()[0] != b'0'
        && text.bytes().all(|b| b.is_ascii_digit())
        && text.parse::<i64>().is_ok_and(|n| n > 0)
}
impl ContactsQuery {
    pub(super) fn validate(&self) -> Result<()> {
        if let Self::OwnedAccount { raw_contact_id } = self {
            require(
                positive_id(raw_contact_id),
                "Contacts raw ID is not canonical",
            )?;
        }
        Ok(())
    }
    pub(super) fn arguments(&self) -> Result<Vec<CString>> {
        self.validate()?;
        // No shell wrapper is executed. This fixed Java entry requires the
        // selected app_process64/content.jar roles and their sealed classpath.
        let (table, columns, predicate) = match self {
            Self::RawRows => ("raw_contacts", RAW_COLUMNS, None),
            Self::FixtureNames => (
                "data",
                NAME_COLUMNS,
                Some(format!(
                    "mimetype='{NAME_MIME}' AND (data1='{NAME}' OR data1='{EDITED}')"
                )),
            ),
            Self::OwnedAccount { raw_contact_id } => (
                "raw_contacts",
                ACCOUNT_COLUMNS,
                Some(format!("_id={raw_contact_id}")),
            ),
        };
        let mut argv = vec![
            "/system/bin/app_process64".to_owned(),
            "/system/bin".to_owned(),
            "com.android.commands.content.Content".to_owned(),
            "query".to_owned(),
            "--user".to_owned(),
            "0".to_owned(),
            "--uri".to_owned(),
            format!("content://com.android.contacts/{table}"),
            "--projection".to_owned(),
            columns.join(":"),
        ];
        if let Some(predicate) = predicate {
            argv.extend(["--where".to_owned(), predicate]);
        }
        argv.into_iter()
            .map(|s| CString::new(s).map_err(|_| reject("NUL in fixed Contacts query")))
            .collect()
    }
    fn columns(&self) -> &'static [&'static str] {
        match self {
            Self::RawRows => RAW_COLUMNS,
            Self::FixtureNames => NAME_COLUMNS,
            Self::OwnedAccount { .. } => ACCOUNT_COLUMNS,
        }
    }
}

#[derive(Debug, PartialEq, Eq)]
struct Row(Vec<Option<String>>);
fn parse_rows(raw: &str, columns: &[&str]) -> Result<Vec<Row>> {
    require(raw.len() <= OUTPUT_LIMIT, "Contacts response bound")?;
    if raw.trim() == "No result found." {
        return Ok(Vec::new());
    }
    require(!raw.trim().is_empty(), "empty Contacts response is unknown")?;
    let mut rows = Vec::new();
    for (number, line) in raw.lines().enumerate() {
        require(number < MAX_ROWS, "Contacts row count bound")?;
        let prefix = format!("Row: {number} ");
        let row = line
            .strip_prefix(&prefix)
            .ok_or_else(|| reject("Contacts row numbering or output format changed"))?;
        let fields: Vec<&str> = row.split(", ").collect();
        require(
            fields.len() == columns.len(),
            "Contacts projection arity changed",
        )?;
        let values = columns
            .iter()
            .zip(fields)
            .map(|(column, field)| {
                let prefix = format!("{column}=");
                let value = field
                    .strip_prefix(&prefix)
                    .ok_or_else(|| reject("Contacts projection order changed"))?;
                require(
                    value.is_ascii() && !value.bytes().any(|b| b.is_ascii_control()),
                    "Contacts fixed projection contains unexpected text",
                )?;
                Ok(match value {
                    "NULL" | "null" => None,
                    _ => Some(value.to_owned()),
                })
            })
            .collect::<Result<Vec<_>>>()?;
        rows.push(Row(values));
    }
    require(!rows.is_empty(), "Contacts response had no recognized rows")?;
    Ok(rows)
}
fn field(row: &Row, at: usize) -> Result<&str> {
    row.0
        .get(at)
        .and_then(Option::as_deref)
        .ok_or_else(|| reject("Contacts required identity field is null"))
}
fn id(row: &Row, at: usize) -> Result<&str> {
    let value = field(row, at)?;
    require(
        positive_id(value),
        "Contacts identity is not a positive canonical ID",
    )?;
    Ok(value)
}

/// Not deserializable and never a success/ownership grant. Only the native
/// read flow below populates this from actual query output.
struct ContactState {
    raw: Vec<Row>,
    names: Vec<Row>,
    account: Option<Row>,
}
#[derive(Clone, Debug, PartialEq, Eq)]
struct ContactIdentity {
    raw: String,
    contact: String,
    name_data: String,
}
impl ContactState {
    fn validate_shape(&self) -> Result<()> {
        let mut ids = BTreeSet::new();
        for row in &self.raw {
            require(
                row.0.len() == RAW_COLUMNS.len(),
                "Contacts raw projection differs",
            )?;
            let raw = id(row, 0)?;
            require(ids.insert(raw), "duplicate raw Contacts ID")?;
            require(matches!(field(row, 2)?, "0" | "1"), "invalid deleted state")?;
        }
        require(self.names.len() <= 1, "fixture marker is not unique")?;
        if let Some(name) = self.names.first() {
            require(
                name.0.len() == NAME_COLUMNS.len(),
                "Contacts name projection differs",
            )?;
            id(name, 0)?;
            id(name, 1)?;
            id(name, 2)?;
            require(field(name, 3)? == NAME_MIME, "fixture MIME differs")?;
            require(
                matches!(field(name, 4)?, NAME | EDITED),
                "fixture name differs",
            )?;
            let account = self
                .account
                .as_ref()
                .ok_or_else(|| reject("fixture account row was not actually read"))?;
            require(
                account.0.len() == ACCOUNT_COLUMNS.len(),
                "Contacts account projection differs",
            )?;
            require(
                id(account, 0)? == id(name, 1)?,
                "fixture raw/account identity differs",
            )?;
        } else {
            require(
                self.account.is_none(),
                "account read without observed fixture",
            )?;
        }
        Ok(())
    }
    fn empty_baseline(&self) -> Result<()> {
        self.validate_shape()?;
        require(
            self.raw.is_empty() && self.names.is_empty() && self.account.is_none(),
            "Contacts baseline is not empty or the fixture already exists",
        )
    }
    fn owned(
        &self,
        expected_name: &str,
        original: Option<&ContactIdentity>,
    ) -> Result<ContactIdentity> {
        self.validate_shape()?;
        require(
            matches!(expected_name, NAME | EDITED),
            "unexpected fixture name",
        )?;
        let name = self
            .names
            .first()
            .ok_or_else(|| reject("owned marker absent"))?;
        let raw = self
            .account
            .as_ref()
            .ok_or_else(|| reject("owned account absent"))?;
        require(
            field(name, 4)? == expected_name,
            "expected fixture name not observed",
        )?;
        require(
            raw.0[2].is_none() && raw.0[3].is_none() && raw.0[4].is_none(),
            "fixture is not device-local with all three account fields null",
        )?;
        require(
            field(raw, 5)? == "0" && id(raw, 1)? == id(name, 2)?,
            "fixture is deleted or its aggregate identity changed",
        )?;
        require(
            self.raw.len() == 1
                && id(&self.raw[0], 0)? == id(raw, 0)?
                && id(&self.raw[0], 1)? == id(raw, 1)?
                && field(&self.raw[0], 2)? == "0",
            "Contacts set contains an unowned or changed row",
        )?;
        let identity = ContactIdentity {
            raw: id(raw, 0)?.to_owned(),
            contact: id(raw, 1)?.to_owned(),
            name_data: id(name, 0)?.to_owned(),
        };
        if let Some(original) = original {
            require(
                identity.raw == original.raw && identity.contact == original.contact,
                "edit/reopen changed the original fixture record identity",
            )?;
        }
        Ok(identity)
    }
    fn deleted(&self, original: &ContactIdentity) -> Result<()> {
        self.validate_shape()?;
        require(
            self.names.is_empty() && self.account.is_none(),
            "fixture still visible",
        )?;
        for row in &self.raw {
            require(
                id(row, 0)? == original.raw && field(row, 2)? == "1",
                "a live or unowned contact remains after delete",
            )?;
        }
        Ok(())
    }
}

struct ContactsProbe<'borrow, 'owner> {
    ready: Workflow<'borrow, 'owner>,
    framework: WorkflowFramework,
    expected: [ApplicationInspection; 2],
    receipts: Vec<ReadReceipt>,
    deadline: Instant,
}
fn complete(receipt: &ReadReceipt) -> bool {
    receipt.cgroup_removed
        && receipt.successful_retirement()
        && receipt.query_waitid_code == libc::CLD_EXITED
        && receipt.query_waitid_status == 0
}
impl AndroidProbe for ContactsProbe<'_, '_> {
    fn epoch(&mut self) -> std::result::Result<RuntimeEpoch, String> {
        let value = self
            .ready
            .application_epoch(&self.framework)
            .map_err(|e| e.to_string())?;
        require(Instant::now() < self.deadline, "Contacts workflow deadline")
            .map_err(|e| e.to_string())?;
        Ok(value)
    }
    fn command(&mut self, args: &[String]) -> std::result::Result<String, String> {
        (|| -> Result<String> {
            require(
                Instant::now() < self.deadline && self.receipts.len() < 400,
                "Contacts workflow deadline or command bound",
            )?;
            let query = ApplicationRead::from_command(args)?;
            let allowed = match &query {
                ApplicationRead::PackageIdentity { package, user }
                | ApplicationRead::PackagePaths { package, user } => self
                    .expected
                    .iter()
                    .any(|x| x.package == *package && x.user == *user),
                ApplicationRead::ApkStat { path } | ApplicationRead::ApkSha256 { path } => self
                    .expected
                    .iter()
                    .flat_map(|x| &x.apks)
                    .any(|a| a.path == *path),
            };
            require(
                allowed,
                "Contacts inspection escaped the two bound package APK sets",
            )?;
            let result = self
                .ready
                .run_application_read_before(&query, self.deadline)
                .map_err(external)?;
            require(
                complete(&result.receipt),
                "Contacts read child retirement incomplete",
            )?;
            self.receipts.push(result.receipt);
            require(Instant::now() < self.deadline, "Contacts workflow deadline")?;
            Ok(result.output)
        })()
        .map_err(|e| e.to_string())
    }
}
impl ContactsProbe<'_, '_> {
    fn provider(&mut self, query: ContactsQuery) -> Result<Vec<Row>> {
        require(
            Instant::now() < self.deadline && self.receipts.len() < 400,
            "Contacts workflow deadline or command bound",
        )?;
        let before = self.epoch().map_err(external)?;
        let result = self
            .ready
            .run_application_contacts_read(&query, self.deadline)
            .map_err(external)?;
        require(
            complete(&result.receipt),
            "Contacts provider child retirement incomplete",
        )?;
        let rows = parse_rows(&result.output, query.columns())?;
        self.receipts.push(result.receipt);
        require(
            self.epoch().map_err(external)? == before,
            "Contacts provider read crossed a framework epoch",
        )?;
        Ok(rows)
    }
    fn state(&mut self) -> Result<ContactState> {
        let raw = self.provider(ContactsQuery::RawRows)?;
        let names = self.provider(ContactsQuery::FixtureNames)?;
        require(names.len() <= 1, "fixture marker is not unique")?;
        let account = if let Some(name) = names.first() {
            let raw_contact_id = id(name, 1)?.to_owned();
            let mut rows = self.provider(ContactsQuery::OwnedAccount { raw_contact_id })?;
            require(
                rows.len() == 1,
                "owned fixture account row is missing or ambiguous",
            )?;
            Some(rows.remove(0))
        } else {
            None
        };
        let state = ContactState {
            raw,
            names,
            account,
        };
        state.validate_shape()?;
        Ok(state)
    }
    fn inspect_bound(&mut self) -> Result<()> {
        for expected in self.expected.clone() {
            let actual =
                crate::control::application_probe::inspect(self, &expected.package, expected.user)
                    .map_err(external)?;
            require(
                actual == expected,
                "Contacts package/version/UID/APK/epoch changed",
            )?;
        }
        Ok(())
    }
}

/// Evidence for an actually observed empty provider baseline. It deliberately
/// contains no executable capability and no ContactsSearch acceptance flag.
#[derive(Debug, Serialize)]
pub(crate) struct ContactsBaselineObservation {
    schema: &'static str,
    epoch: RuntimeEpoch,
    package_identities: [ApplicationInspection; 2],
    empty_raw_contacts: bool,
    fixture_markers_absent: bool,
    actual_provider_reads: usize,
    retired_commands: usize,
    receipts: Vec<ReadReceipt>,
    ui_create_edit_search_delete_qualified: bool,
    account_topology_qualified: bool,
    whole_application_qualified: bool,
}

fn fixed_expected(
    contacts: &ApplicationInspection,
    provider: &ApplicationInspection,
) -> Result<()> {
    for (item, package, uid, version, path, bytes, digest) in [
        (
            contacts,
            "com.android.contacts",
            10055,
            10734,
            "/product/priv-app/Contacts/Contacts.apk",
            11839391,
            "11f8be5fd46dd79ee4f7524d5d1334e21ce0f9e23892b2940a5b6091e2f349d0",
        ),
        (
            provider,
            "com.android.providers.contacts",
            10015,
            37,
            "/system/priv-app/ContactsProvider/ContactsProvider.apk",
            872865,
            "9a8d8238565ff977a025ad6eb3f1496b5bd2ea9c819b3229278d62e29da0c313",
        ),
    ] {
        require(
            item.package == package
                && item.user == 0
                && item.uid == uid
                && item.version_code == version
                && item.apks.len() == 1,
            "Contacts fixture package contract differs",
        )?;
        let apk = &item.apks[0];
        require(
            apk.path == path && apk.bytes == bytes && apk.sha256 == digest,
            "Contacts fixture complete selected APK contract differs",
        )?;
    }
    require(
        contacts.epoch == provider.epoch,
        "Contacts/provider epochs differ",
    )
}

pub(super) fn baseline(
    mut ready: Workflow<'_, '_>,
    contacts: &ApplicationInspection,
    provider: &ApplicationInspection,
) -> Result<ContactsBaselineObservation> {
    fixed_expected(contacts, provider)?;
    let deadline = Instant::now() + WORK_LIMIT;
    let framework = ready.observe_application_framework().map_err(external)?;
    let mut probe = ContactsProbe {
        ready,
        framework,
        expected: [contacts.clone(), provider.clone()],
        receipts: Vec::new(),
        deadline,
    };
    require(
        probe.epoch().map_err(external)? == contacts.epoch,
        "Contacts expected original framework is no longer current",
    )?;
    probe.inspect_bound()?;
    let before_reads = probe.receipts.len();
    probe.state()?.empty_baseline()?;
    let provider_reads = probe.receipts.len() - before_reads;
    require(
        provider_reads == 2,
        "empty baseline did not use both fixed provider reads",
    )?;
    probe.inspect_bound()?;
    require(
        probe.epoch().map_err(external)? == contacts.epoch,
        "Contacts baseline lost its original epoch",
    )?;
    require(
        Instant::now() < deadline && probe.receipts.iter().all(complete),
        "Contacts baseline deadline or full command retirement incomplete",
    )?;
    Ok(ContactsBaselineObservation {
        schema: "droidloom-owned-contacts-empty-baseline-v1",
        epoch: contacts.epoch.clone(),
        package_identities: probe.expected,
        empty_raw_contacts: true,
        fixture_markers_absent: true,
        actual_provider_reads: provider_reads,
        retired_commands: probe.receipts.len(),
        receipts: probe.receipts,
        ui_create_edit_search_delete_qualified: false,
        account_topology_qualified: false,
        whole_application_qualified: false,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    fn state(name: &str, raw: &str, contact: &str) -> ContactState {
        ContactState {
            raw: parse_rows(&format!("Row: 0 _id={raw}, contact_id={contact}, deleted=0\n"), RAW_COLUMNS).unwrap(),
            names: parse_rows(&format!("Row: 0 _id=3, raw_contact_id={raw}, contact_id={contact}, mimetype={NAME_MIME}, data1={name}\n"), NAME_COLUMNS).unwrap(),
            account: Some(parse_rows(&format!("Row: 0 _id={raw}, contact_id={contact}, account_name=NULL, account_type=NULL, data_set=NULL, deleted=0\n"), ACCOUNT_COLUMNS).unwrap().remove(0)),
        }
    }
    #[test]
    fn contacts_provider_parser_rejects_ambiguous_empty_numbering_projection_and_ids() {
        assert!(
            parse_rows("No result found.\n", RAW_COLUMNS)
                .unwrap()
                .is_empty()
        );
        for raw in [
            "",
            "\n",
            "Row: 1 _id=1, contact_id=2, deleted=0\n",
            "Row: 00 _id=1, contact_id=2, deleted=0\n",
            "Row: 0 contact_id=2, _id=1, deleted=0\n",
            "Row: 0 _id=1, contact_id=2, deleted=0, account_name=x\n",
        ] {
            assert!(parse_rows(raw, RAW_COLUMNS).is_err());
        }
        let mut bad = state(NAME, "1", "2");
        bad.raw[0].0[0] = Some("01".into());
        assert!(bad.validate_shape().is_err());
        assert!(
            ContactsQuery::OwnedAccount {
                raw_contact_id: "1 OR 1=1".into()
            }
            .arguments()
            .is_err()
        );
        assert!(
            serde_json::from_str::<ContactsQuery>(
                r#"{"contacts_read":"RawRows","uri":"content://com.android.contacts/data"}"#
            )
            .is_err()
        );
        for (query, wire) in [
            (ContactsQuery::RawRows, r#"{"contacts_read":"RawRows"}"#),
            (
                ContactsQuery::FixtureNames,
                r#"{"contacts_read":"FixtureNames"}"#,
            ),
            (
                ContactsQuery::OwnedAccount {
                    raw_contact_id: "9".into(),
                },
                r#"{"contacts_read":"OwnedAccount","raw_contact_id":"9"}"#,
            ),
        ] {
            assert_eq!(serde_json::from_str::<ContactsQuery>(wire).unwrap(), query);
            assert_eq!(serde_json::to_string(&query).unwrap(), wire);
        }
        for wire in [
            r#"{"contacts_read":"FixtureNames","uri":"content://com.android.contacts/data"}"#,
            r#"{"contacts_read":"RawRows","raw_contact_id":null}"#,
            r#"{"contacts_read":"FixtureNames","raw_contact_id":"9"}"#,
            r#"{"contacts_read":"OwnedAccount","raw_contact_id":"9","uri":"content://com.android.contacts/data"}"#,
            r#"{"contacts_read":"OwnedAccount"}"#,
            r#"{"contacts_read":"OwnedAccount","raw_contact_id":null}"#,
            r#"{"contacts_read":"RawRows","contacts_read":"FixtureNames"}"#,
            r#"{"contacts_read":"OwnedAccount","raw_contact_id":"9","raw_contact_id":"10"}"#,
        ] {
            assert!(
                serde_json::from_str::<ContactsQuery>(wire).is_err(),
                "{wire}"
            );
        }
    }
    #[test]
    fn contacts_identity_preserves_local_account_record_edit_and_delete_contract() {
        let initial = state(NAME, "1", "2");
        assert!(initial.empty_baseline().is_err());
        let owned = initial.owned(NAME, None).unwrap();
        state(EDITED, "1", "2").owned(EDITED, Some(&owned)).unwrap();
        assert!(state(EDITED, "1", "4").owned(EDITED, Some(&owned)).is_err());
        for contact in [Some("4".to_owned()), None] {
            let mut changed_raw = state(EDITED, "1", "2");
            changed_raw.raw[0].0[1] = contact;
            assert!(changed_raw.owned(EDITED, Some(&owned)).is_err());
        }
        let mut foreign = state(EDITED, "1", "2");
        foreign.account.as_mut().unwrap().0[3] = Some("external.account".into());
        assert!(foreign.owned(EDITED, Some(&owned)).is_err());
        let empty = ContactState {
            raw: vec![],
            names: vec![],
            account: None,
        };
        empty.empty_baseline().unwrap();
        empty.deleted(&owned).unwrap();
        let tombstone = ContactState {
            raw: parse_rows("Row: 0 _id=1, contact_id=2, deleted=1\n", RAW_COLUMNS).unwrap(),
            names: vec![],
            account: None,
        };
        tombstone.deleted(&owned).unwrap();
        let other = ContactState {
            raw: parse_rows("Row: 0 _id=9, contact_id=2, deleted=1\n", RAW_COLUMNS).unwrap(),
            names: vec![],
            account: None,
        };
        assert!(other.deleted(&owned).is_err());
    }
    #[test]
    fn contacts_provider_argv_has_only_fixed_read_tables_and_fixture_predicates() {
        for query in [
            ContactsQuery::RawRows,
            ContactsQuery::FixtureNames,
            ContactsQuery::OwnedAccount {
                raw_contact_id: "9".into(),
            },
        ] {
            let args = query
                .arguments()
                .unwrap()
                .into_iter()
                .map(|x| x.into_string().unwrap())
                .collect::<Vec<_>>();
            assert_eq!(args[0], "/system/bin/app_process64");
            assert_eq!(args[2], "com.android.commands.content.Content");
            assert_eq!(&args[3..6], &["query", "--user", "0"]);
            assert!(ApplicationRead::from_command(&args).is_err());
            assert!(
                !args
                    .iter()
                    .any(|x| matches!(x.as_str(), "insert" | "delete" | "update" | "call"))
            );
        }
    }
}
