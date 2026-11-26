//! Canonical, bounded public transport for the one compiled native leaf cohort.
//! The public archive supplies bytes only; the compiled member table is authority.
use super::*;
use std::ops::Range;

const BLOCK: usize = 512;
const MAX_ARCHIVE: u64 = 32 * 1024 * 1024;

fn padding(bytes: u64) -> Result<u64> {
    bytes
        .checked_add(511)
        .map(|n| n / 512 * 512)
        .ok_or_else(|| "cohort archive size overflow".into())
}
pub(super) fn size(expected: &BTreeMap<String, Pin>) -> Result<u64> {
    if expected.is_empty() || expected.len() > MAX_FILES {
        return fail("invalid compiled archive member count");
    }
    let mut total = 1024u64;
    for (name, pin) in expected {
        relative(name)?;
        if !sha_shape(&pin.sha256)
            || (pin.bytes > MAX_FILE
                && (name != "bin/held-namespace-entry"
                    || pin.bytes != FIXED_HELPER_BYTES
                    || pin.sha256 != FIXED_HELPER_SHA256))
        {
            return fail("archive member is outside the compiled source bounds");
        }
        header(name, pin)?;
        total = total
            .checked_add(512 + padding(pin.bytes)?)
            .ok_or("cohort archive size overflow")?;
    }
    if total > MAX_ARCHIVE {
        return fail("compiled cohort archive exceeds bound");
    }
    Ok(total)
}
fn octal(field: &mut [u8], value: u64) -> Result<()> {
    let s = format!("{:0width$o}", value, width = field.len() - 1);
    if s.len() != field.len() - 1 {
        return fail("ustar field overflow");
    }
    field[..s.len()].copy_from_slice(s.as_bytes());
    field[s.len()] = 0;
    Ok(())
}
fn header(name: &str, pin: &Pin) -> Result<[u8; BLOCK]> {
    relative(name)?;
    if !name.is_ascii() {
        return fail("compiled archive name must be ASCII");
    }
    let (prefix, short) = if name.len() <= 100 {
        ("", name)
    } else {
        let at = name
            .rmatch_indices('/')
            .find_map(|(i, _)| (i <= 155 && name.len() - i - 1 <= 100).then_some(i))
            .ok_or("compiled ustar name too long")?;
        (&name[..at], &name[at + 1..])
    };
    let mut h = [0u8; BLOCK];
    h[..short.len()].copy_from_slice(short.as_bytes());
    octal(
        &mut h[100..108],
        if name == "bin/held-namespace-entry" {
            0o755
        } else {
            0o444
        },
    )?;
    octal(&mut h[108..116], 0)?;
    octal(&mut h[116..124], 0)?;
    octal(&mut h[124..136], pin.bytes)?;
    octal(&mut h[136..148], 0)?;
    h[148..156].fill(b' ');
    h[156] = b'0';
    h[257..263].copy_from_slice(b"ustar\0");
    h[263..265].copy_from_slice(b"00");
    h[345..345 + prefix.len()].copy_from_slice(prefix.as_bytes());
    let sum: u64 = h.iter().map(|x| *x as u64).sum();
    let check = format!("{sum:06o}\0 ");
    if check.len() != 8 {
        return fail("ustar checksum overflow");
    }
    h[148..156].copy_from_slice(check.as_bytes());
    Ok(h)
}
pub(super) fn build(
    outputs: &BTreeMap<String, Vec<u8>>,
    expected: &BTreeMap<String, Pin>,
) -> Result<Vec<u8>> {
    if outputs.keys().ne(expected.keys()) {
        return fail("archive source set differs from compiled members");
    }
    let mut raw = Vec::with_capacity(size(expected)? as usize);
    for (name, pin) in expected {
        let body = outputs.get(name).ok_or("archive member unavailable")?;
        check_bytes(body, pin)?;
        raw.extend_from_slice(&header(name, pin)?);
        raw.extend_from_slice(body);
        raw.resize(raw.len() + (padding(pin.bytes)? - pin.bytes) as usize, 0);
    }
    raw.resize(raw.len() + 2 * BLOCK, 0);
    verify(&raw, expected)?;
    Ok(raw)
}
pub(super) fn verify(
    raw: &[u8],
    expected: &BTreeMap<String, Pin>,
) -> Result<Vec<(String, Range<usize>)>> {
    if raw.len() as u64 != size(expected)? {
        return fail("public archive has a wrong exact size or trailing bytes");
    }
    let mut offset = 0usize;
    let mut rows = Vec::new();
    for (name, pin) in expected {
        // Comparing the entire canonical header also rejects links, PAX/GNU
        // extensions, duplicates, reordered names, traversal, modes and extra metadata.
        if raw.get(offset..offset + BLOCK) != Some(header(name, pin)?.as_slice()) {
            return fail(format!(
                "public archive header differs at fixed member {name}"
            ));
        }
        offset += BLOCK;
        let end = offset
            .checked_add(pin.bytes as usize)
            .ok_or("archive range overflow")?;
        let body = raw.get(offset..end).ok_or("short archive body")?;
        check_bytes(body, pin)?;
        rows.push((name.clone(), offset..end));
        let padded = offset + padding(pin.bytes)? as usize;
        if raw
            .get(end..padded)
            .ok_or("short archive padding")?
            .iter()
            .any(|b| *b != 0)
        {
            return fail("nonzero archive padding");
        }
        offset = padded;
    }
    if raw.get(offset..) != Some([0u8; 1024].as_slice()) {
        return fail("archive exact EOF differs");
    }
    Ok(rows)
}
fn read_archive(fd: &mut File, expected: u64) -> Result<Vec<u8>> {
    if expected > MAX_ARCHIVE {
        return fail("public archive exceeds fixed bound");
    }
    fd.seek(SeekFrom::Start(0))?;
    let mut raw = Vec::with_capacity(expected as usize);
    fd.take(expected + 1).read_to_end(&mut raw)?;
    if raw.len() as u64 != expected {
        return fail("short or growing public archive");
    }
    Ok(raw)
}
pub(super) struct PublicArchive {
    root: File,
    name: String,
    file: File,
    before: Node,
    pub(super) pin: Pin,
    pub(super) raw: Vec<u8>,
}
impl PublicArchive {
    pub(super) fn open(path: &Path, expected: &BTreeMap<String, Pin>) -> Result<Self> {
        absolute(path)?;
        let root = File::open("/")?;
        let name = path
            .strip_prefix("/")?
            .to_str()
            .ok_or("public archive path is not UTF-8")?
            .to_owned();
        // Unlike trusted source directories, a public archive's owner grants no
        // authority. openat2 still rejects every symlink and magic-link component.
        let mut file = beneath(&root, &name, false)?;
        let m = file.metadata()?;
        if !m.is_file() || m.nlink() != 1 || m.mode() & 0o7000 != 0 || m.len() != size(expected)? {
            return fail(
                "public archive is not a single-link regular file of the exact compiled size",
            );
        }
        let before = node(&m)?;
        let raw = read_archive(&mut file, m.len())?;
        verify(&raw, expected)?;
        let pin = Pin {
            path: path.to_str().ok_or("invalid archive path")?.into(),
            bytes: raw.len() as u64,
            sha256: digest(&raw),
        };
        let mut archive = Self {
            root,
            name,
            file,
            before,
            pin,
            raw,
        };
        archive.recheck()?;
        Ok(archive)
    }
    pub(super) fn recheck(&mut self) -> Result<()> {
        if node(&self.file.metadata()?)? != self.before
            || node(&beneath(&self.root, &self.name, false)?.metadata()?)? != self.before
        {
            return fail("public archive held or named identity changed");
        }
        if digest(&read_archive(&mut self.file, self.pin.bytes)?) != self.pin.sha256
            || node(&self.file.metadata()?)? != self.before
            || node(&beneath(&self.root, &self.name, false)?.metadata()?)? != self.before
        {
            return fail("public archive full bookend changed");
        }
        Ok(())
    }
    pub(super) fn evidence(&self) -> Value {
        json!({"pin":self.pin,"identity":self.before,"whole_sha256_is_observed":true,
        "caller_digest_accepted":false,"source_owner_is_authority":false,
        "member_authority":"compiled source recipe","held_full_bookends_equal":true})
    }
}
pub(super) fn write_output(
    destination: &OutputTree,
    raw: &[u8],
    expected: &BTreeMap<String, Pin>,
) -> Result<StagedFile> {
    verify(raw, expected)?;
    destination.guard()?;
    let n = CString::new("COHORT.tar")?;
    let fd = unsafe {
        libc::openat(
            destination.root.as_raw_fd(),
            n.as_ptr(),
            libc::O_RDWR | libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_CREAT | libc::O_EXCL,
            0o400,
        )
    };
    if fd < 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    let mut file = unsafe { File::from_raw_fd(fd) };
    file.write_all(raw)?;
    file.sync_all()?;
    let identity = node(&file.metadata()?)?;
    if identity.links != 1
        || identity.uid != unsafe { libc::geteuid() }
        || identity.mode & 0o7777 != 0o400
        || read_archive(&mut file, raw.len() as u64)? != raw
        || node(&file.metadata()?)? != identity
        || node(&beneath(&destination.root, "COHORT.tar", false)?.metadata()?)? != identity
    {
        return fail("normal cohort package failed complete held readback");
    }
    destination.root.sync_all()?;
    destination.guard()?;
    Ok(StagedFile {
        relative_path: "COHORT.tar".into(),
        bytes: raw.len() as u64,
        sha256: digest(raw),
        identity,
    })
}
pub(super) fn recheck_output(destination: &OutputTree, pin: &StagedFile) -> Result<()> {
    destination.guard()?;
    if pin.relative_path != "COHORT.tar" {
        return fail("wrong cohort package path");
    }
    let mut file = beneath(&destination.root, &pin.relative_path, false)?;
    if node(&file.metadata()?)? != pin.identity
        || digest(&read_archive(&mut file, pin.bytes)?) != pin.sha256
        || node(&file.metadata()?)? != pin.identity
    {
        return fail("normal package changed");
    }
    destination.guard()
}
#[cfg(test)]
mod tests {
    use super::*;
    fn fixture() -> (BTreeMap<String, Vec<u8>>, BTreeMap<String, Pin>) {
        let body = b"source-owned\n".to_vec();
        let name = "source/one.py".to_string();
        let pin = Pin {
            path: format!("{}/{name}", cohort::ROOT),
            bytes: body.len() as u64,
            sha256: digest(&body),
        };
        (
            BTreeMap::from([(name.clone(), body)]),
            BTreeMap::from([(name, pin)]),
        )
    }
    #[test]
    fn cohort_package_exact_format_rejects_malformed_headers_bodies_and_eof() {
        let (outputs, pins) = fixture();
        let good = build(&outputs, &pins).unwrap();
        assert_eq!(verify(&good, &pins).unwrap().len(), 1);
        for (offset, value) in [
            (0, b'/'),
            (100, b'7'),
            (108, b'1'),
            (156, b'1'),
            (156, b'2'),
            (156, b'x'),
            (156, b'g'),
            (257, b'G'),
            (BLOCK, b'X'),
            (BLOCK + 13, 1),
        ] {
            let mut bad = good.clone();
            bad[offset] = value;
            assert!(verify(&bad, &pins).is_err(), "offset {offset}");
        }
        for suffix in [vec![0u8; 512], vec![1u8]] {
            let mut bad = good.clone();
            bad.extend(suffix);
            assert!(verify(&bad, &pins).is_err());
        }
        let mut short = good.clone();
        short.pop();
        assert!(verify(&short, &pins).is_err());
        let mut duplicate = good[..1024].to_vec();
        duplicate.extend_from_slice(&good);
        assert!(verify(&duplicate, &pins).is_err());
    }
    #[test]
    fn cohort_package_held_public_input_rejects_changed_linked_and_replaced_files() {
        use std::os::unix::fs::symlink;
        let (outputs, pins) = fixture();
        let good = build(&outputs, &pins).unwrap();
        let tmp = tempfile::tempdir().unwrap();
        let p = tmp.path().join("COHORT.tar");
        fs::write(&p, &good).unwrap();
        let mut held = PublicArchive::open(&p, &pins).unwrap();
        held.recheck().unwrap();
        fs::rename(&p, tmp.path().join("old")).unwrap();
        fs::write(&p, &good).unwrap();
        assert!(held.recheck().is_err());
        fs::remove_file(&p).unwrap();
        symlink(tmp.path().join("old"), &p).unwrap();
        assert!(PublicArchive::open(&p, &pins).is_err());
        fs::remove_file(&p).unwrap();
        fs::hard_link(tmp.path().join("old"), &p).unwrap();
        assert!(PublicArchive::open(&p, &pins).is_err());
    }
}
