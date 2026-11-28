//! Source-owned publication of the exact admitted APK cohort. This is a cold
//! byte-copy boundary only; installation and business acceptance remain runtime
//! observations. All source and destination descriptors stay independently held.
use super::CurrentPublicMaterials;
use crate::{
    Result, boot_files::FilePin, boot_public_apks::VerifiedApkSource,
    cold_original_data::labels::WorkingLabelBatch, ensure, fs, model::Identity,
};
use rustix::fs::{Mode, OFlags, RenameFlags};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::File,
    os::unix::fs::FileExt,
    path::{Path, PathBuf},
};
const BASE: &str = "/var/lib/droidloom-public-apks";
const COHORT: &str = "4abd5c5d0a8ac89e739b2ba6dd508435a1d355b9ce975ba5ceacb50c1ee4a4a0";
const COUNT: usize = 67;

fn names(directory: &File) -> Result<Vec<String>> {
    let before = fs::stat(directory)?;
    let mut names = Vec::new();
    for entry in rustix::fs::Dir::read_from(directory)? {
        let entry = entry?;
        let name = entry.file_name().to_str()?;
        if name != "." && name != ".." {
            names.push(name.to_owned());
        }
        ensure(names.len() <= COUNT, "APK cohort has too many members")?;
    }
    names.sort();
    ensure(
        fs::stat(directory)? == before,
        "APK cohort changed during bounded enumeration",
    )?;
    Ok(names)
}
fn directory(file: &File) -> Result<Identity> {
    let id = fs::stat(file)?;
    ensure(
        id.mode == 0o40700 && id.uid == 0 && id.gid == 0 && fs::xattrs(file)?.is_empty(),
        "APK publication requires an actual protected root directory",
    )?;
    Ok(id)
}
fn open_directory(parent: &File, name: &str) -> Result<File> {
    Ok(File::from(rustix::fs::openat(
        parent,
        name,
        OFlags::RDONLY | OFlags::DIRECTORY | OFlags::CLOEXEC | OFlags::NOFOLLOW,
        Mode::empty(),
    )?))
}
fn open_readonly(parent: &File, name: &str) -> Result<File> {
    Ok(File::from(rustix::fs::openat(
        parent,
        name,
        OFlags::RDONLY | OFlags::CLOEXEC | OFlags::NOFOLLOW | OFlags::NONBLOCK,
        Mode::empty(),
    )?))
}
struct Node {
    path: PathBuf,
    file: File,
    identity: Identity,
}
impl Node {
    fn guard(&self) -> Result<()> {
        ensure(
            fs::stat(&self.file)? == self.identity && fs::xattrs(&self.file)?.is_empty(),
            "held APK publication inode or privilege attributes changed",
        )?;
        let tree = fs::Tree::open("/", 0)?;
        ensure(
            tree.identity(&fs::absolute_string(&self.path)?)? == self.identity,
            "named APK publication no longer denotes its held inode",
        )
    }
}
struct CopiedApk {
    node: Node,
    pin: FilePin,
    source: FilePin,
    source_identity: Identity,
}
pub(crate) struct PublishedApks {
    candidate: String,
    base: Node,
    cohort: Node,
    files: Vec<CopiedApk>,
    names: Vec<String>,
    created: bool,
}
fn validate_file(file: &File, source: &VerifiedApkSource<'_>) -> Result<Identity> {
    let id = fs::stat(file)?;
    let expected = source.pin();
    ensure(
        id.mode == 0o100400
            && id.uid == 0
            && id.gid == 0
            && id.nlink == 1
            && id.size == expected.bytes
            && (id.dev, id.ino) != (source.identity().dev, source.identity().ino)
            && fs::xattrs(file)?.is_empty(),
        "published APK is not an independent protected complete ordinary file",
    )?;
    ensure(
        crate::boot_public_apks::held_apk_hash(file, expected.bytes)? == expected.sha256
            && file.read_at(&mut [0], id.size)? == 0
            && fs::stat(file)? == id,
        "published APK complete readback differs from its actual source",
    )?;
    source.revalidate()?;
    Ok(id)
}
impl PublishedApks {
    pub(crate) fn publish(materials: &CurrentPublicMaterials, candidate: &str) -> Result<Self> {
        ensure(
            rustix::process::geteuid().is_root()
                && rustix::process::getegid().as_raw() == 0
                && fs::valid_digest(candidate)
                && materials.admission.selection.sha256 == COHORT
                && materials.admission.apk_file_count == COUNT,
            "APK publication requires the actual root owner and the compiled current cohort",
        )?;
        materials.revalidate()?;
        let sources = materials.actual.apk_sources()?;
        ensure(
            sources.len() == COUNT,
            "actual held APK roster differs from the current cohort",
        )?;
        let mut by_name = BTreeMap::new();
        let mut source_nodes = BTreeSet::new();
        for source in sources {
            ensure(
                fs::valid_digest(&source.pin().sha256)
                    && source_nodes.insert((source.identity().dev, source.identity().ino))
                    && by_name
                        .insert(format!("{}.apk", source.pin().sha256), source)
                        .is_none(),
                "APK cohort has duplicate content or aliased source objects",
            )?;
        }
        let library = fs::Tree::open("/", 0)?.dir("/var/lib")?;
        match rustix::fs::mkdirat(
            &library,
            "droidloom-public-apks",
            Mode::from_raw_mode(0o700),
        ) {
            Ok(()) => library.sync_all()?,
            Err(rustix::io::Errno::EXIST) => {}
            Err(e) => return Err(e.into()),
        }
        let base_file = open_directory(&library, "droidloom-public-apks")?;
        directory(&base_file)?;
        let mut created = false;
        let cohort_file = match open_directory(&base_file, COHORT) {
            Ok(file) => file,
            Err(error) => {
                // Only actual ENOENT admits a new private staging directory.
                let absent =
                    rustix::fs::statat(&base_file, COHORT, rustix::fs::AtFlags::SYMLINK_NOFOLLOW)
                        .is_err_and(|e| e == rustix::io::Errno::NOENT);
                ensure(
                    absent,
                    &format!("existing APK cohort cannot be opened: {error}"),
                )?;
                let staging = format!(".working-publication-{candidate}");
                rustix::fs::mkdirat(&base_file, staging.as_str(), Mode::from_raw_mode(0o700))?;
                base_file.sync_all()?;
                let temporary = open_directory(&base_file, &staging)?;
                directory(&temporary)?;
                ensure(
                    names(&temporary)?.is_empty(),
                    "new APK staging directory is not empty",
                )?;
                for (name, source) in &by_name {
                    source.revalidate()?;
                    let mut output = File::from(rustix::fs::openat(
                        &temporary,
                        name.as_str(),
                        OFlags::RDWR
                            | OFlags::CREATE
                            | OFlags::EXCL
                            | OFlags::CLOEXEC
                            | OFlags::NOFOLLOW,
                        Mode::from_raw_mode(0o400),
                    )?);
                    source.copy_to(&mut output)?;
                    let copied = validate_file(&output, source)?;
                    let named = open_readonly(&temporary, name)?;
                    ensure(
                        fs::stat(&named)? == copied,
                        "APK destination changed before durable publication",
                    )?;
                    temporary.sync_all()?;
                }
                let expected = by_name.keys().cloned().collect::<Vec<_>>();
                ensure(
                    names(&temporary)? == expected,
                    "staged APK membership differs",
                )?;
                temporary.sync_all()?;
                rustix::fs::syncfs(&temporary)?;
                rustix::fs::renameat_with(
                    &base_file,
                    staging.as_str(),
                    &base_file,
                    COHORT,
                    RenameFlags::NOREPLACE,
                )?;
                base_file.sync_all()?;
                created = true;
                let published = open_directory(&base_file, COHORT)?;
                let old = fs::stat(&temporary)?;
                let new = fs::stat(&published)?;
                ensure(
                    old == new,
                    "atomic APK publication did not retain the staged inode",
                )?;
                published
            }
        };
        directory(&cohort_file)?;
        let expected_names = by_name.keys().cloned().collect::<Vec<_>>();
        ensure(
            names(&cohort_file)? == expected_names,
            "published APK cohort is not the exact closed source roster",
        )?;
        let mut files = Vec::new();
        let mut destination_nodes = BTreeSet::new();
        for (name, source) in &by_name {
            let file = open_readonly(&cohort_file, name)?;
            let identity = validate_file(&file, source)?;
            ensure(
                !source_nodes.contains(&(identity.dev, identity.ino))
                    && destination_nodes.insert((identity.dev, identity.ino)),
                "APK publication reuses a source or another destination inode",
            )?;
            let path = Path::new(BASE).join(COHORT).join(name);
            files.push(CopiedApk {
                node: Node {
                    path: path.clone(),
                    file,
                    identity,
                },
                pin: FilePin {
                    path,
                    bytes: source.pin().bytes,
                    sha256: source.pin().sha256.clone(),
                },
                source: source.pin().clone(),
                source_identity: source.identity().clone(),
            });
        }
        cohort_file.sync_all()?;
        base_file.sync_all()?;
        let base_identity = directory(&base_file)?;
        let cohort_identity = directory(&cohort_file)?;
        materials.revalidate()?;
        let value = Self {
            candidate: candidate.into(),
            base: Node {
                path: PathBuf::from(BASE),
                file: base_file,
                identity: base_identity,
            },
            cohort: Node {
                path: Path::new(BASE).join(COHORT),
                file: cohort_file,
                identity: cohort_identity,
            },
            files,
            names: expected_names,
            created,
        };
        value.revalidate()?;
        Ok(value)
    }
    pub(crate) fn revalidate(&self) -> Result<()> {
        self.base.guard()?;
        self.cohort.guard()?;
        ensure(
            self.files.len() == COUNT && names(&self.cohort.file)? == self.names,
            "held published APK membership changed",
        )?;
        for file in &self.files {
            file.node.guard()?;
        }
        self.base.guard()?;
        self.cohort.guard()
    }
    pub(crate) fn accept_labels(&mut self, batch: &WorkingLabelBatch) -> Result<()> {
        for proof in batch.records() {
            ensure(
                batch.candidate_id() == self.candidate,
                "APK label proof belongs to another working candidate",
            )?;
            for node in std::iter::once(&mut self.base)
                .chain(std::iter::once(&mut self.cohort))
                .chain(self.files.iter_mut().map(|f| &mut f.node))
            {
                if proof.paths().iter().any(|path| path == &node.path) {
                    node.identity =
                        proof.require_held_transition(&node.path, &node.file, &node.identity)?;
                }
            }
        }
        self.revalidate()
    }
    pub(crate) fn report(&self) -> Value {
        json!({"schema":"droidloom.working-public-apk-publication.v1",
            "candidate_id":self.candidate,"selection_sha256":COHORT,
            "cohort_directory":self.cohort.path,"directory_identity":self.cohort.identity,
            "new_independent_copy":self.created,
            "existing_complete_cohort_revalidated":!self.created,
            "apk_file_count":self.files.len(),
            "files":self.files.iter().map(|f|json!({"source":f.source,"source_identity":f.source_identity,
                "destination":f.pin,"destination_identity":f.node.identity,
                "complete_source_and_destination_sha256_verified":true,
                "independent_inode_verified":true})).collect::<Vec<_>>(),
            "applications_installed":0,"application_business_accepted":false,
            "production_ready":false})
    }
}
