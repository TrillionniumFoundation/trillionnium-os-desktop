//! The installed cohort is a source closure, not a business qualification.
//! Every member comes from the compiled recipe. The caller supplies no path,
//! digest map, owner or mode. File descriptors remain held for the invocation.
use super::*;
use std::time::Instant;

pub(crate) struct InstalledCohort {
    tree: InputTree,
    files: BTreeMap<String, Held>,
}
fn before(end: Instant) -> Result<()> {
    if Instant::now() >= end {
        fail("installed cohort original budget expired")
    } else {
        Ok(())
    }
}
impl InstalledCohort {
    pub(crate) fn capture(end: Instant) -> Result<Self> {
        if unsafe { libc::getuid() } != 0
            || unsafe { libc::geteuid() } != 0
            || unsafe { libc::getgid() } != 0
            || unsafe { libc::getegid() } != 0
        {
            return fail("normal installed cohort observation requires the original root operator");
        }
        before(end)?;
        let expected = cohort::installed_members()?;
        let mut tree = InputTree::open(Path::new(cohort::ROOT))?;
        if tree.inventory()? != expected.keys().cloned().collect() {
            return fail("normal installed cohort has missing or extra members");
        }
        for fd in std::iter::once(&tree.root).chain(tree.directories.values().map(|v| &v.0)) {
            let m = fd.metadata()?;
            if m.uid() != 0 || m.gid() != 0 || m.mode() & 0o7777 != 0o755 {
                return fail("normal installed cohort directory owner or mode differs");
            }
        }
        let mut files = BTreeMap::new();
        for (name, pin) in expected {
            before(end)?;
            let file = Held::open(&tree.root, &name, &pin)?;
            let mode = if name == "bin/held-namespace-entry" {
                0o755
            } else {
                0o444
            };
            if file.before.uid != 0 || file.before.gid != 0 || file.before.mode & 0o7777 != mode {
                return fail("normal installed cohort member owner or mode differs");
            }
            files.insert(name, file);
        }
        tree.recheck()?;
        before(end)?;
        Ok(Self { tree, files })
    }
    pub(crate) fn recheck(&mut self, end: Instant) -> Result<()> {
        before(end)?;
        self.tree.recheck()?;
        for file in self.files.values_mut() {
            before(end)?;
            file.recheck(&self.tree.root)?;
        }
        self.tree.recheck()?;
        before(end)
    }
    pub(crate) fn recipe(&self) -> Value {
        cohort::compiled_recipe_pin()
    }
    pub(crate) fn collector(&self) -> Result<&Path> {
        const NAME: &str = "source/main/kernel_native_observation.py";
        let pin = &self
            .files
            .get(NAME)
            .ok_or("compiled normal baseline collector missing")?
            .pin;
        if pin.path != format!("{}/{NAME}", cohort::ROOT) {
            return fail("fixed baseline collector differs");
        }
        Ok(Path::new(&pin.path))
    }
}
