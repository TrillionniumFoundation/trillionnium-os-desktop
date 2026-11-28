//! Files created by this actual preparation invocation, held until Ready/ACK.
//! A stored pin is only a comparison. It cannot reconstruct this owner.
use super::*;
use std::{collections::BTreeMap, path::{Component, PathBuf}};

const MAX_FILES: usize = 4096;
const MAX_DIRECTORIES: usize = 512;
const MAX_FILE: u64 = 512 * 1024 * 1024;
const MAX_TOTAL: u64 = 8 * 1024 * 1024 * 1024;
const MAX_JSON: u64 = 4 * 1024 * 1024;
struct HeldDirectory { file: File, identity: [u64;5] }
struct HeldFile { file: File, identity: [i128;9], reference: Value }
pub(super) struct Artifacts {
    roots: Vec<PathBuf>,
    directories: BTreeMap<PathBuf,HeldDirectory>,
    files: BTreeMap<PathBuf,HeldFile>,
    total: u64,
}
fn ordinary(path: &Path) -> bool {
    path.is_absolute() && path.components().all(|p|matches!(p,Component::RootDir|Component::Normal(_)))
}
fn hash_file(file: &mut File, end: Instant) -> Result<String> {
    file.seek(SeekFrom::Start(0))?;
    let mut hash=Sha256::new();
    let mut buffer=[0u8;65536];
    loop {
        check_before(end)?;
        let n=file.read(&mut buffer)?;
        if n==0 {break}
        hash.update(&buffer[..n]);
    }
    Ok(hex::encode(hash.finalize()))
}
fn digest_shape(s:&str)->bool {
    s.len()==64 && s.bytes().all(|c|c.is_ascii_digit()||(b'a'..=b'f').contains(&c))
}
impl Artifacts {
    pub(super) fn new()->Self {Self {roots:Vec::new(),directories:BTreeMap::new(),files:BTreeMap::new(),total:0}}
    fn directory(&mut self,path:&Path)->Result<()> {
        if let Some(held)=self.directories.get(path) {
            if directory_identity(&held.file.metadata()?)!=held.identity
                || directory_identity(&fs::symlink_metadata(path)?)!=held.identity {
                return fail("normal preparation directory changed");
            }
            return Ok(())
        }
        if self.directories.len()>=MAX_DIRECTORIES || !ordinary(path) || path.canonicalize()?!=path {
            return fail("normal preparation directory bound or canonical path differs");
        }
        let file=OpenOptions::new().read(true)
            .custom_flags(libc::O_DIRECTORY|libc::O_NOFOLLOW|libc::O_CLOEXEC).open(path)?;
        let m=file.metadata()?;
        if !m.is_dir() || m.uid()!=0 || m.gid()!=0 || m.mode()&0o7022!=0 {
            return fail("normal preparation directory is not protected root storage");
        }
        let identity=directory_identity(&m);
        if directory_identity(&fs::symlink_metadata(path)?)!=identity {return fail("preparation directory moved during capture")}
        self.directories.insert(path.into(),HeldDirectory{file,identity});
        Ok(())
    }
    pub(super) fn hold_tree(&mut self,root:&Path,end:Instant)->Result<()> {
        check_before(end)?;
        if root.parent()!=Some(Path::new(QUALIFICATION_ROOT)) || !ordinary(root)
            || root.file_name().and_then(|s|s.to_str()).is_none_or(|s|
                s.len()>128 || !s.bytes().all(|c|c.is_ascii_alphanumeric()||c==b'-')) {
            return fail("preparation can hold only a source-created root at the fixed qualification location");
        }
        for p in root.ancestors() {self.directory(p)?;}
        if !self.roots.iter().any(|p|p==root) {self.roots.push(root.into());}
        let mut pending=vec![(root.to_path_buf(),0usize)];
        while let Some((directory,depth))=pending.pop() {
            check_before(end)?;
            if depth>6 {return fail("preparation result tree exceeds its depth bound")}
            self.directory(&directory)?;
            let mut entries=fs::read_dir(&directory)?.collect::<std::io::Result<Vec<_>>>()?;
            entries.sort_by_key(|e|e.file_name());
            for entry in entries {
                check_before(end)?;
                let name=entry.file_name().into_string().map_err(|_|"non-UTF8 preparation member")?;
                if name.is_empty() || name.len()>160 || name=="." || name==".."
                    || !name.bytes().all(|c|c.is_ascii_alphanumeric()||b"_.-".contains(&c)) {
                    return fail("preparation result member has an unbounded name");
                }
                let path=directory.join(&name);
                let kind=entry.file_type()?;
                if kind.is_dir() {pending.push((path,depth+1));}
                else if kind.is_file() {self.hold_file(&path,end)?;}
                else {return fail("preparation result contains a link or special file")}
            }
            self.directory(&directory)?;
        }
        Ok(())
    }
    fn hold_file(&mut self,path:&Path,end:Instant)->Result<()> {
        if self.files.contains_key(path) {return self.guard_file(path,end)}
        if self.files.len()>=MAX_FILES || !self.roots.iter().any(|root|path.starts_with(root)) {
            return fail("preparation result file is not in this invocation's bounded roots");
        }
        self.directory(path.parent().ok_or("preparation member has no parent")?)?;
        let mut file=OpenOptions::new().read(true)
            .custom_flags(libc::O_NOFOLLOW|libc::O_CLOEXEC|libc::O_NONBLOCK).open(path)?;
        let m=file.metadata()?;
        if !m.is_file() || m.uid()!=0 || m.gid()!=0 || m.nlink()!=1 || m.len()>MAX_FILE
            || ![0o400,0o600].contains(&(m.mode()&0o7777)) {
            return fail("preparation member is not an exact protected single-link regular file");
        }
        let total=self.total.checked_add(m.len()).ok_or("preparation total overflow")?;
        if total>MAX_TOTAL {return fail("preparation result bytes exceed their fixed bound")}
        let identity=node(&m); let digest=hash_file(&mut file,end)?;
        if node(&file.metadata()?)!=identity || node(&fs::symlink_metadata(path)?)!=identity {
            return fail("preparation member changed during its first complete read");
        }
        let reference=json!({"path":path,"bytes":m.len(),"sha256":digest});
        self.files.insert(path.into(),HeldFile{file,identity,reference});self.total=total;
        Ok(())
    }
    fn guard_file(&mut self,path:&Path,end:Instant)->Result<()> {
        check_before(end)?;
        let held=self.files.get_mut(path).ok_or("held preparation member absent")?;
        let named=OpenOptions::new().read(true)
            .custom_flags(libc::O_NOFOLLOW|libc::O_CLOEXEC|libc::O_NONBLOCK).open(path)?;
        if node(&named.metadata()?)!=held.identity || node(&held.file.metadata()?)!=held.identity {
            return fail("preparation member held/named identity changed");
        }
        if hash_file(&mut held.file,end)?!=held.reference["sha256"].as_str().ok_or("held digest absent")?
            || node(&held.file.metadata()?)!=held.identity || node(&named.metadata()?)!=held.identity {
            return fail("preparation member complete byte bookend differs");
        }
        Ok(())
    }
    pub(super) fn reference(&mut self,path:&Path,end:Instant)->Result<Value> {
        self.guard_file(path,end)?;
        Ok(self.files.get(path).ok_or("preparation file absent")?.reference.clone())
    }
    pub(super) fn require_reference(&mut self,pin:&Value,end:Instant)->Result<PathBuf> {
        let object=pin.as_object().ok_or("preparation reference is not an object")?;
        if object.len()!=3 || !object.contains_key("path") || !object.contains_key("bytes")
            || !object.get("sha256").and_then(Value::as_str).is_some_and(digest_shape) {
            return fail("preparation reference has unexpected fields");
        }
        let path=PathBuf::from(object["path"].as_str().ok_or("preparation reference path absent")?);
        if !ordinary(&path) || self.reference(&path,end)?!=*pin {
            return fail("printed preparation reference is not the held actual new file");
        }
        Ok(path)
    }
    pub(super) fn json(&mut self,pin:&Value,end:Instant)->Result<Value> {
        let path=self.require_reference(pin,end)?;
        let held=self.files.get_mut(&path).ok_or("held JSON absent")?;
        if held.identity[6]<0 || held.identity[6] as u64>MAX_JSON {return fail("preparation JSON exceeds bound")}
        held.file.seek(SeekFrom::Start(0))?;
        let mut body=Vec::new();Read::by_ref(&mut held.file).take(MAX_JSON+1).read_to_end(&mut body)?;
        if body.len() as i128!=held.identity[6] || sha(&body)!=held.reference["sha256"].as_str().ok_or("held JSON digest absent")?
            || node(&held.file.metadata()?)!=held.identity {return fail("held preparation JSON changed")}
        let value=serde_json::from_slice(&body)?;
        self.guard_file(&path,end)?;
        Ok(value)
    }
    pub(super) fn guard(&mut self,end:Instant)->Result<()> {
        check_before(end)?;
        let paths=self.directories.keys().cloned().collect::<Vec<_>>();
        for path in paths {self.directory(&path)?;}
        let paths=self.files.keys().cloned().collect::<Vec<_>>();
        for path in paths {self.guard_file(&path,end)?;}
        check_before(end)
    }
    pub(super) fn comparison(&self)->Value {
        json!({"files":self.files.len(),"directories":self.directories.len(),"bytes":self.total,
            "roots":self.roots,"whole_files_held":true,"business_authority":false})
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn preparation_result_pins_do_not_create_a_file_owner() {
        let mut held=Artifacts::new();
        let end=Instant::now()+Duration::from_secs(2);
        for pin in [
            json!({"path":"/tmp/caller","bytes":1,"sha256":"a".repeat(64)}),
            json!({"path":"/var/lib/droidloom/qualification/pocket4/native-leaf-x/REQUEST.json",
                "bytes":1,"sha256":"a".repeat(64),"accepted":true}),
        ] {assert!(held.require_reference(&pin,end).is_err());}
    }
    #[test]
    fn preparation_storage_does_not_accept_dot_or_relative_paths() {
        assert!(!ordinary(Path::new("caller/result.json")));
        assert!(!ordinary(Path::new("/var/lib/../caller")));
        assert!(ordinary(Path::new("/var/lib/droidloom/qualification/pocket4/native-leaf-A/REQUEST.json")));
    }
}
