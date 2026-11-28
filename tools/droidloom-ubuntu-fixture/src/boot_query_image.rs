//! Read the sealed original query roles back from the actual generated ext4.
//! No mounted filesystem or writable debugfs command is used here.
use crate::{
    Result, boot_files,
    boot_query::{self, fixed},
    ensure, fs,
};
use serde_json::{Value, json};
use std::{collections::BTreeSet, path::Path};

fn quoted(path: &str) -> Result<String> {
    ensure(
        path.starts_with('/') && !path.bytes().any(|b| b < 32 || b == b'"' || b == b'\\'),
        "unsupported fixed query readback path",
    )?;
    Ok(format!("\"{path}\""))
}

fn number(line: &str, key: &str, radix: u32) -> Result<u64> {
    let fields: Vec<_> = line.split_ascii_whitespace().collect();
    let positions: Vec<_> = fields
        .iter()
        .enumerate()
        .filter(|(_, word)| **word == key)
        .collect();
    ensure(
        positions.len() == 1,
        "ext4 query inode field missing or repeated",
    )?;
    Ok(u64::from_str_radix(
        fields
            .get(positions[0].0 + 1)
            .ok_or("truncated query inode field")?,
        radix,
    )?)
}

fn one_line<'a>(raw: &'a str, prefix: &str) -> Result<&'a str> {
    let lines: Vec<_> = raw
        .lines()
        .filter(|line| line.starts_with(prefix))
        .collect();
    ensure(
        lines.len() == 1,
        "ext4 query inode record missing or repeated",
    )?;
    Ok(lines[0])
}

fn sealed_stat(role: fixed::FixedQueryInput, raw: &str) -> Result<u64> {
    ensure(
        raw.len() <= 65536 && !raw.contains('\0'),
        "unbounded ext4 query inode record",
    )?;
    let head = one_line(raw, "Inode:")?;
    let identity = one_line(raw, "User:")?;
    let links = one_line(raw, "Links:")?;
    let tokens: Vec<_> = head.split_ascii_whitespace().collect();
    let types: Vec<_> = tokens
        .iter()
        .enumerate()
        .filter(|(_, v)| **v == "Type:")
        .collect();
    ensure(
        types.len() == 1 && tokens.get(types[0].0 + 1) == Some(&"regular"),
        "actual ext4 query input is not one regular inode",
    )?;
    let inode = number(head, "Inode:", 10)?;
    ensure(
        inode > 0
            && number(head, "Mode:", 8)? == u64::from(role.installed_mode())
            && number(identity, "User:", 10)? == 0
            && number(identity, "Group:", 10)? == 0
            && number(identity, "Size:", 10)? == role.bytes
            && number(links, "Links:", 10)? == 1,
        "actual ext4 query owner, sealed mode, size or singleton link differs",
    )?;
    Ok(inode)
}

fn sealed_xattrs(role: fixed::FixedQueryInput, raw: &str, label: &[u8]) -> Result<()> {
    ensure(
        raw.len() <= 65536 && !raw.contains('\0'),
        "unbounded ext4 query xattr inventory",
    )?;
    // run_logged retains stderr; remove only the normal reader version banner.
    let lines: Vec<_> = raw
        .lines()
        .filter(|line| !line.trim().is_empty() && !line.starts_with("debugfs "))
        .collect();
    ensure(
        label == role.original_label
            && lines.len() == 2
            && lines[0] == "Extended attributes:"
            && lines[1].trim_start().starts_with(&format!(
                "security.selinux ({}) = ",
                role.original_label.len()
            )),
        "actual ext4 query input has a changed label or extra extended attributes",
    )
}

pub fn verify(root: &Path, work: &Path, disk: &Path, runtime: &str) -> Result<Value> {
    boot_query::verify_sealed(root, runtime)?;
    let paths = boot_query::guest_paths(runtime)?;
    let output = work.join("fixed-query-readback");
    boot_files::private_dir(&output)?;
    let mut rows = Vec::new();
    let mut inodes = BTreeSet::new();
    for (guest, role) in paths.iter().zip(fixed::INPUTS) {
        let body = output.join(role.output_name);
        let dumped = boot_files::run_logged(
            &output,
            &format!("{}-body", role.output_name),
            "/usr/sbin/debugfs",
            &[
                "-R".into(),
                format!(
                    "dump {} {}",
                    quoted(guest)?,
                    quoted(&fs::absolute_string(&body)?)?
                ),
                disk.to_string_lossy().into(),
            ],
            30,
        )?;
        let actual = boot_files::pin_file(&body)?;
        ensure(
            actual.bytes == role.bytes && actual.sha256 == role.sha256,
            "actual ext4 fixed query whole-file bytes differ",
        )?;
        let stat = boot_files::run_logged(
            &output,
            &format!("{}-stat", role.output_name),
            "/usr/sbin/debugfs",
            &[
                "-R".into(),
                format!("stat {}", quoted(guest)?),
                disk.to_string_lossy().into(),
            ],
            30,
        )?;
        let stat_text = String::from_utf8(boot_files::read_pin(&stat.log, 65536)?)?;
        let inode = sealed_stat(role, &stat_text)?;
        ensure(
            inodes.insert(inode),
            "fixed query roles unexpectedly share an ext4 inode",
        )?;
        let attrs = boot_files::run_logged(
            &output,
            &format!("{}-attrs", role.output_name),
            "/usr/sbin/debugfs",
            &[
                "-R".into(),
                format!("ea_list {}", quoted(guest)?),
                disk.to_string_lossy().into(),
            ],
            30,
        )?;
        let attrs_text = String::from_utf8(boot_files::read_pin(&attrs.log, 65536)?)?;
        let label = output.join(format!("{}-label", role.output_name));
        let labelled = boot_files::run_logged(
            &output,
            &format!("{}-label", role.output_name),
            "/usr/sbin/debugfs",
            &[
                "-R".into(),
                format!(
                    "ea_get -f {} {} security.selinux",
                    quoted(&fs::absolute_string(&label)?)?,
                    quoted(guest)?
                ),
                disk.to_string_lossy().into(),
            ],
            30,
        )?;
        let label_pin = boot_files::pin_file(&label)?;
        sealed_xattrs(role, &attrs_text, &boot_files::read_pin(&label_pin, 256)?)?;
        rows.push(json!({"path":guest,"inode":inode,"bytes":actual.bytes,"sha256":actual.sha256,
            "mode":role.installed_mode(),"uid":0,"gid":0,"links":1,
            "label_hex":hex::encode(role.original_label),"extra_xattrs_absent":true,
            "body_readback":dumped,"inode_readback":stat,"xattrs_readback":attrs,"label_readback":labelled}));
    }
    boot_query::verify_sealed(root, runtime)?;
    Ok(
        json!({"input_scope":fixed::INPUT_SCOPE,"runtime_manifest_sha256":runtime,
        "files":rows,"all_four_original_inputs_matched":true,"readonly_ext4_reader":true,
        "query_executions":0,"guest_qualified":false}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn sealed_query_stat_rejects_source_shell_group_extra_links_and_mutated_size() {
        let role = fixed::INPUTS[0];
        let valid = format!(
            "debugfs 1.47.2\nInode: 13   Type: regular    Mode:  0555   Flags: 0x80000\nUser:     0   Group:     0   Project: 0   Size: {}\nLinks: 1   Blockcount: 104\n",
            role.bytes
        );
        assert_eq!(sealed_stat(role, &valid).unwrap(), 13);
        for (from, to) in [
            ("Group:     0", "Group: 2000"),
            ("Mode:  0555", "Mode: 0755"),
            ("Links: 1", "Links: 2"),
            ("Size: 52160", "Size: 52161"),
            ("Type: regular", "Type: symlink"),
        ] {
            assert!(
                sealed_stat(role, &valid.replace(from, to)).is_err(),
                "{from}"
            );
        }
        assert!(sealed_stat(role, &format!("{valid}Links: 1\n")).is_err());
    }
    #[test]
    fn ext4_query_inventory_rejects_capabilities_extra_labels_and_reader_errors() {
        let role = fixed::INPUTS[0];
        let listing = format!(
            "debugfs 1.47.2\nExtended attributes:\n  security.selinux ({}) = \"original\"\n",
            role.original_label.len()
        );
        assert!(sealed_xattrs(role, &listing, role.original_label).is_ok());
        assert!(sealed_xattrs(role, &listing, b"u:object_r:var_lib_t:s0\0").is_err());
        for extra in [
            "  security.capability (20) = ...\n",
            "  user.extra (1) = x\n",
            "  security.selinux (24) = duplicate\n",
            "File not found by ext2_lookup\n",
        ] {
            assert!(
                sealed_xattrs(role, &format!("{listing}{extra}"), role.original_label).is_err()
            );
        }
    }
}
