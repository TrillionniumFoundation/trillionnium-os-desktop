//! Shared strict original-query inode and xattr parsing for both normal publishers.
use super::{fixed, require, Result};

fn number(line: &str, key: &str, radix: u32) -> Result<u64> {
    let fields: Vec<_> = line.split_ascii_whitespace().collect();
    require(
        fields.iter().filter(|&&word| word == key).count() == 1,
        "one actual original query metadata field",
    )?;
    let at = fields.iter().position(|&word| word == key).unwrap();
    Ok(u64::from_str_radix(
        fields.get(at + 1).ok_or("original query metadata value")?,
        radix,
    )?)
}

pub(super) fn original_stat(role: fixed::FixedQueryInput, raw: &[u8]) -> Result<u64> {
    require(
        raw.len() <= 8192 && !raw.contains(&0),
        "bounded original query stat",
    )?;
    let text = std::str::from_utf8(raw)?;
    let lines: Vec<_> = text.lines().collect();
    let first = lines.first().ok_or("original query stat is empty")?;
    let words: Vec<_> = first.split_ascii_whitespace().collect();
    let at = words
        .iter()
        .position(|&word| word == "Type:")
        .ok_or("original query type")?;
    let ids: Vec<_> = lines
        .iter()
        .filter(|line| line.starts_with("User:"))
        .collect();
    let links: Vec<_> = lines
        .iter()
        .filter(|line| line.starts_with("Links:"))
        .collect();
    require(
        words.iter().filter(|&&word| word == "Type:").count() == 1
            && words.get(at + 1) == Some(&"regular")
            && ids.len() == 1
            && links.len() == 1,
        "one actual regular original query inode record",
    )?;
    let inode = number(first, "Inode:", 10)?;
    require(
        inode > 0
            && (number(first, "Mode:", 8)? | 0o100000) == u64::from(role.original_mode)
            && number(ids[0], "User:", 10)? == 0
            && number(ids[0], "Group:", 10)? == u64::from(role.original_gid)
            && number(ids[0], "Size:", 10)? == role.bytes
            && number(links[0], "Links:", 10)? == 1,
        "original query source mode, shell group, singleton inode or complete byte count differs",
    )?;
    Ok(inode)
}

pub(super) fn original_xattrs(role: fixed::FixedQueryInput, listing: &[u8], label: &[u8]) -> Result<()> {
    require(
        listing.len() <= 8192,
        "bounded original query xattr inventory",
    )?;
    let rows: Vec<_> = std::str::from_utf8(listing)?
        .lines()
        .filter(|line| !line.trim().is_empty())
        .collect();
    require(
        label == role.original_label
            && rows.len() == 2
            && rows[0] == "Extended attributes:"
            && rows[1].trim_start().starts_with(&format!(
                "security.selinux ({}) = ",
                role.original_label.len()
            )),
        "complete original query label and xattr inventory must contain no file capabilities or extra attributes",
    )
}

