//! Stage the current four state fixtures and the unchanged IHG helper.
//! Private signing material is never in the compiled member table.
use droidloom_supervisor::prebuilt_native_helpers::{HelperKind,MEMBERS,ALL_KINDS};
use std::{collections::BTreeSet,fs::{self,File,OpenOptions},io::{self,Write},
 os::unix::fs::{DirBuilderExt,FileExt,MetadataExt,OpenOptionsExt,PermissionsExt},path::{Path,PathBuf}};
#[path="working_prebuilt_inputs.rs"]
mod inputs;
fn bad(s:&str)->io::Error {io::Error::new(io::ErrorKind::InvalidData,s)}
fn relative(kind:HelperKind)->&'static Path {Path::new(kind.root().trim_start_matches('/'))}
fn protected_parent(stage:&Path,path:&Path)->io::Result<()> {
    let rest=path.strip_prefix(stage).map_err(io::Error::other)?;
    let mut here=stage.to_path_buf();
    for part in std::iter::once(None).chain(rest.components().map(Some)) {
        if let Some(part)=part {
            let std::path::Component::Normal(name)=part else{return Err(bad("nonrelative helper stage member"));};
            here.push(name);
        }
        let m=fs::symlink_metadata(&here)?;
        if !m.is_dir() || m.mode()&0o022!=0 {return Err(bad("helper stage parent is aliased or writable by another group"));}
    }
    Ok(())
}
fn mkdirs(stage:&Path,path:&Path)->io::Result<()> {
    let mut here=stage.to_path_buf();protected_parent(stage,stage)?;
    for part in path.strip_prefix(stage).map_err(io::Error::other)?.components() {
        let std::path::Component::Normal(name)=part else{return Err(bad("helper stage member is not relative"));};
        here.push(name);
        if !here.try_exists()? {
            fs::DirBuilder::new().mode(0o700).create(&here)?;
            let directory=OpenOptions::new().read(true)
                .custom_flags(0x10000|0x20000|0x80000).open(&here)?;
            let before=directory.metadata()?;
            directory.set_permissions(fs::Permissions::from_mode(0o755))?;
            let after=directory.metadata()?;let named=fs::symlink_metadata(&here)?;
            let identity=|m:&fs::Metadata|(m.dev(),m.ino(),m.mode(),m.uid(),m.gid(),m.nlink(),m.len(),m.mtime(),m.mtime_nsec(),m.ctime(),m.ctime_nsec());
            if (before.dev(),before.ino(),before.uid(),before.gid())!=(after.dev(),after.ino(),after.uid(),after.gid())
                || after.mode()!=0o40755 || identity(&after)!=identity(&named) {
                return Err(bad("new helper stage directory changed during mode publication"));
            }
            directory.sync_all()?;
        }
        protected_parent(stage,&here)?;
    }
    Ok(())
}
fn inventory(root:&Path,at:&Path,out:&mut BTreeSet<PathBuf>)->io::Result<()> {
    let entries=fs::read_dir(at)?.collect::<io::Result<Vec<_>>>()?;
    if entries.len()>32 {return Err(bad("helper output directory is outside its fixed roster"));}
    for entry in entries {
        let path=entry.path();let m=fs::symlink_metadata(&path)?;
        if m.is_dir() {if m.mode()&0o7777!=0o755{return Err(bad("helper output directory mode"));}inventory(root,&path,out)?;}
        else if m.is_file() && m.nlink()==1 {out.insert(path.strip_prefix(root).map_err(io::Error::other)?.into());}
        else {return Err(bad("helper output contains a link or special file"));}
    }
    Ok(())
}
pub fn stage_prebuilt_helpers(stage:&Path)->io::Result<Vec<PathBuf>> {
    let external=inputs::ExternalInputs::capture()?;
    protected_parent(stage,stage)?;
    for kind in ALL_KINDS {
        let root=stage.join(relative(kind));mkdirs(stage,root.parent().ok_or_else(||bad("missing bundle parent"))?)?;
        if root.try_exists()? {return Err(bad("normal helper bundle output must be create-only"));}
    }
    let mut paths=Vec::new();
    for member in MEMBERS {
        let relative=relative(member.kind).join(member.relative);
        let path=stage.join(&relative);mkdirs(stage,path.parent().ok_or_else(||bad("missing member parent"))?)?;
        let mut f=OpenOptions::new().read(true).write(true).create_new(true)
            .custom_flags(0x20000|0x80000).mode(0o600).open(&path)?;
        let external_body;
        let body=if let Some(raw)=member.embedded_body()?{raw}else{external_body=external.body(member)?;&external_body};
        f.write_all(body)?;f.sync_all()?;
        f.set_permissions(fs::Permissions::from_mode(0o444))?;f.sync_all()?;
        let mut body=vec![0;member.bytes as usize];f.read_exact_at(&mut body,0)?;
        member.verify_body(&body)?;
        if f.read_at(&mut[0],member.bytes)?!=0 || f.metadata()?.nlink()!=1 {return Err(bad("normal helper stage failed complete readback"));}
        paths.push(relative);
    }
    for kind in ALL_KINDS {File::open(stage.join(relative(kind)))?.sync_all()?;}
    verify_staged_prebuilt_helpers(stage)?;external.guard()?;Ok(paths)
}
pub(crate) fn verify_staged_prebuilt_helpers(stage:&Path)->io::Result<()> {
    for kind in ALL_KINDS {
        let root=stage.join(relative(kind));protected_parent(stage,&root)?;
        let mut actual=BTreeSet::new();inventory(&root,&root,&mut actual)?;
        let expected=MEMBERS.iter().filter(|m|m.kind==kind).map(|m|PathBuf::from(m.relative)).collect();
        if actual!=expected{return Err(bad("normal helper stage member roster differs"));}
        for m in MEMBERS.iter().filter(|m|m.kind==kind) {
            let p=root.join(m.relative);protected_parent(stage,p.parent().ok_or_else(||bad("helper parent absent"))?)?;
            let f=OpenOptions::new().read(true).custom_flags(0x20000|0x80000).open(&p)?;
            let before=f.metadata()?;
            let identity=|v:&fs::Metadata|(v.dev(),v.ino(),v.mode(),v.uid(),v.gid(),v.nlink(),v.len(),v.mtime(),v.mtime_nsec(),v.ctime(),v.ctime_nsec());
            if before.mode()!=0o100444 || before.nlink()!=1 || before.len()!=m.bytes{return Err(bad("normal helper stage metadata differs"));}
            let mut body=vec![0;m.bytes as usize];f.read_exact_at(&mut body,0)?;
            m.verify_body(&body)?;
            if f.read_at(&mut[0],m.bytes)?!=0 || identity(&before)!=identity(&f.metadata()?)
                || identity(&before)!=identity(&fs::symlink_metadata(&p)?) {return Err(bad("normal helper stage whole bytes or named inode changed"));}
        }
    }
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    #[ignore="requires ten source-pinned external release inputs under the fixed root"]
    fn prebuilt_helpers_stage_exact_public_roster_rejects_reuse_and_extra_member() {
        let dir=tempfile::tempdir().unwrap();let paths=stage_prebuilt_helpers(dir.path()).unwrap();
        assert_eq!(paths.len(),40);verify_staged_prebuilt_helpers(dir.path()).unwrap();
        assert!(stage_prebuilt_helpers(dir.path()).is_err());
        fs::write(dir.path().join(relative(HelperKind::Saf)).join("unexpected"),b"x").unwrap();
        assert!(verify_staged_prebuilt_helpers(dir.path()).is_err());
    }
}
