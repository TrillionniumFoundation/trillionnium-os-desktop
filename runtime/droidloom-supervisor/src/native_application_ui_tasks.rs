//! Exact task-list comparisons used by the live native UI owner.
//! Parsed bytes are comparison data. Only the source-owned live session may
//! associate these values with an actual launch and authorize its one cleanup.
use std::collections::{BTreeMap, BTreeSet};

#[derive(Debug, Eq, PartialEq)]
pub(super) struct Child {
    pub(super) id: u32,
    pub(super) package: String,
    pub(super) user: u32,
}
#[derive(Debug, Eq, PartialEq)]
pub(super) struct Root {
    display: u32,
    user: u32,
    freeform: bool,
    pub(super) children: Vec<Child>,
}
#[derive(Debug, Eq, PartialEq)]
pub(super) struct Tasks {
    pub(super) roots: BTreeMap<u32, Root>,
    pub(super) ids: BTreeSet<u32>,
}
fn number(value: &str, positive: bool) -> Result<u32, String> {
    if value.is_empty() || !value.bytes().all(|v| v.is_ascii_digit()) {
        return Err("native UI task integer malformed".into());
    }
    let result: u32 = value
        .parse()
        .map_err(|_| "native UI task integer overflow")?;
    if result > i32::MAX as u32 || (positive && result == 0) {
        return Err("native UI task integer outside Android range".into());
    }
    Ok(result)
}
fn field<'a>(line: &'a str, key: &str) -> Result<&'a str, String> {
    let values = line
        .split_ascii_whitespace()
        .filter_map(|s| s.strip_prefix(key))
        .collect::<Vec<_>>();
    match values.as_slice() {
        [value] => Ok(*value),
        _ => Err("native UI task field missing or repeated".into()),
    }
}
impl Tasks {
    pub(super) fn parse(bytes: &[u8]) -> Result<Self, String> {
        if bytes.is_empty()
            || bytes.len() > 65_536
            || bytes
                .iter()
                .any(|b| b.is_ascii_control() && !matches!(*b, b'\n' | b'\r' | b'\t'))
        {
            return Err("native UI task listing is absent or outside fixed bound".into());
        }
        let text = std::str::from_utf8(bytes).map_err(|_| "native UI task list is not UTF-8")?;
        let mut roots = BTreeMap::new();
        let mut ids = BTreeSet::new();
        let mut current = None;
        for line in text.lines().map(str::trim).filter(|line| !line.is_empty()) {
            if let Some(line) = line.strip_prefix("RootTask ") {
                let id = number(field(line, "id=")?, false)?;
                let root = Root {
                    display: number(field(line, "displayId=")?, false)?,
                    user: number(field(line, "userId=")?, false)?,
                    freeform: line
                        .split_ascii_whitespace()
                        .any(|s| s == "mWindowingMode=freeform"),
                    children: Vec::new(),
                };
                if roots.insert(id, root).is_some() || roots.len() > 256 {
                    return Err("native UI duplicate or excessive root tasks".into());
                }
                current = Some(id);
            } else if line.starts_with("configuration=") {
                let root = roots
                    .get_mut(&current.ok_or("native UI task configuration precedes root")?)
                    .ok_or("native UI current root missing")?;
                root.freeform |= line
                    .split_ascii_whitespace()
                    .any(|s| s == "mWindowingMode=freeform");
            } else if let Some(line) = line.strip_prefix("taskId=") {
                let (id, rest) = line
                    .split_once(':')
                    .ok_or("native UI leaf separator absent")?;
                let id = number(id, false)?;
                if !ids.insert(id) || ids.len() > 256 {
                    return Err("native UI duplicate or excessive leaf tasks".into());
                }
                let name = rest
                    .split_ascii_whitespace()
                    .next()
                    .ok_or("native UI task package absent")?;
                let package = if let Some((package, _)) = name.split_once('/') {
                    crate::control::validate_component(name).map_err(|e| e.to_string())?;
                    package
                } else {
                    crate::control::validate_package(name).map_err(|e| e.to_string())?;
                    name
                };
                let child = Child {
                    id,
                    package: package.into(),
                    user: number(field(rest, "userId=")?, false)?,
                };
                let root = roots
                    .get_mut(&current.ok_or("native UI leaf precedes root")?)
                    .ok_or("native UI current root absent")?;
                root.children.push(child);
            } else {
                return Err("native UI unrecognized task-list row".into());
            }
        }
        if roots.is_empty() || ids.is_empty() {
            return Err("native UI nonempty actual task listing required".into());
        }
        Ok(Self { roots, ids })
    }
    pub(super) fn contains_package(&self, package: &str) -> bool {
        self.roots
            .values()
            .any(|root| root.children.iter().any(|child| child.package == package))
    }
    pub(super) fn exact_leaf(&self, id: u32, package: &str) -> bool {
        self.roots.get(&id).is_some_and(|root| {
            root.display == 0
                && root.user == 0
                && root.freeform
                && root.children.len() == 1
                && root.children[0].id == id
                && root.children[0].user == 0
                && root.children[0].package == package
        })
    }
    pub(super) fn shrinking_leaf(&self, id: u32) -> bool {
        !self.ids.contains(&id)
            && self.roots.get(&id).is_some_and(|root| {
                root.display == 0 && root.user == 0 && root.freeform && root.children.is_empty()
            })
    }
    pub(super) fn absent(&self, id: u32) -> bool {
        !self.ids.contains(&id) && !self.roots.contains_key(&id)
    }
    pub(super) fn preserves_other_tasks(&self, before: &BTreeSet<u32>, id: u32) -> bool {
        let mut actual = self.ids.clone();
        actual.remove(&id);
        &actual == before && !before.contains(&id)
    }
}
/// Literal normal RegisterDirect reply only; these numbers cannot reconstruct
/// the opaque live session or become a caller-selected removal argument.
pub(super) fn launch_task(text: &str) -> Result<u32, String> {
    if text.is_empty() || text.len() > 256 || !text.is_ascii() {
        return Err("native UI launch binding outside bound".into());
    }
    let words = text.split_ascii_whitespace().collect::<Vec<_>>();
    if words.len() != 4 {
        return Err("native UI launch binding must contain exactly four fields".into());
    }
    for (word, key) in
        words
            .iter()
            .zip(["object=", "composer_display=", "android_display=", "task="])
    {
        if !word.starts_with(key) {
            return Err("native UI launch binding order or field differs".into());
        }
    }
    let object = words[0].strip_prefix("object=").unwrap();
    let composer = words[1].strip_prefix("composer_display=").unwrap();
    for value in [object, composer] {
        if value.is_empty()
            || !value.bytes().all(|v| v.is_ascii_digit())
            || value.parse::<u64>().ok().is_none_or(|n| n == 0)
        {
            return Err("native UI native object identity is absent".into());
        }
    }
    if number(words[2].strip_prefix("android_display=").unwrap(), false)? != 0 {
        return Err("native UI launch must use built-in display".into());
    }
    number(words[3].strip_prefix("task=").unwrap(), true)
}
#[cfg(test)]
mod tests {
    use super::*;
    fn listing(id: u32, package: &str) -> String {
        format!(
            "RootTask id={id} displayId=0 userId=0\n configuration={{ mWindowingMode=freeform }}\n  taskId={id}: {package}/.Main userId=0 visible=true\n"
        )
    }
    #[test]
    fn native_ui_task_cleanup_requires_one_new_exact_freeform_leaf_and_preserved_others() {
        let original = Tasks::parse(listing(3, "com.android.launcher3").as_bytes()).unwrap();
        let after = Tasks::parse(
            (listing(3, "com.android.launcher3") + &listing(7, "com.android.settings")).as_bytes(),
        )
        .unwrap();
        assert!(after.exact_leaf(7, "com.android.settings"));
        assert!(after.preserves_other_tasks(&original.ids, 7));
        assert!(!after.preserves_other_tasks(&after.ids, 7));
        assert!(original.absent(7));
        for altered in [
            listing(7, "com.android.settings").replace("displayId=0", "displayId=1"),
            listing(7, "com.android.settings").replace("userId=0", "userId=10"),
            listing(7, "com.android.settings")
                .replace("mWindowingMode=freeform", "mWindowingMode=fullscreen"),
            listing(7, "com.android.settings")
                + " taskId=8: com.android.chrome/.Main userId=0 visible=true\n",
        ] {
            assert!(
                !Tasks::parse(altered.as_bytes())
                    .unwrap()
                    .exact_leaf(7, "com.android.settings")
            );
        }
        let lost_other = Tasks::parse(listing(7, "com.android.settings").as_bytes()).unwrap();
        assert!(!lost_other.preserves_other_tasks(&original.ids, 7));
    }
    #[test]
    fn native_ui_task_parser_does_not_convert_errors_duplicates_or_partial_rows_to_absence() {
        let good = listing(3, "com.android.launcher3");
        for bad in [
            "".into(),
            "Error: permission denied\n".into(),
            good.clone() + &good,
            good.replace("displayId=0", "displayId=0 displayId=1"),
            good.replace("taskId=3", "taskId=-3"),
            good.replace("userId=0 visible", "visible"),
            good.clone() + "\0",
            "taskId=3: com.android.launcher3/.Main userId=0\n".into(),
        ] {
            assert!(Tasks::parse(bad.as_bytes()).is_err());
        }
        for bad in [
            "object=1 composer_display=2 android_display=1 task=7",
            "object=0 composer_display=2 android_display=0 task=7",
            "object=1 composer_display=2 android_display=0 task=2147483648",
            "object=1 composer_display=2 android_display=0 task=7 extra=1",
        ] {
            assert!(launch_task(bad).is_err());
        }
        assert_eq!(
            launch_task("object=1 composer_display=2 android_display=0 task=7").unwrap(),
            7
        );
    }
}
