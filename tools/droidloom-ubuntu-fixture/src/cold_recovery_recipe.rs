//! Closed source-recipe dispatch for the existing normal private initramfs
//! producer. Both variants are descriptions only; each concrete implementation
//! independently verifies its actual normal producer and private PID1 owner.
use crate::{
    Result,
    boot_files::{self as files, FilePin},
    ensure,
};
use serde::{Deserialize, Deserializer, Serialize, Serializer, de::Error};
use serde_json::{Value, json};
use std::path::Path;

#[derive(Clone)]
pub(crate) enum RecoveryRecipe {
    Original(crate::cold_original_once_initramfs::RecoveryRecipe),
    Working(crate::cold_working_initramfs::RecoveryRecipe),
}
impl Serialize for RecoveryRecipe {
    fn serialize<S: Serializer>(&self, serializer: S) -> std::result::Result<S::Ok, S::Error> {
        match self {
            Self::Original(value) => value.serialize(serializer),
            Self::Working(value) => value.serialize(serializer),
        }
    }
}
impl<'de> Deserialize<'de> for RecoveryRecipe {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> std::result::Result<Self, D::Error> {
        let raw = Value::deserialize(deserializer)?;
        match raw.get("schema").and_then(Value::as_str) {
            Some(
                "droidloom.original-once-initramfs-recipe.v1"
                | "droidloom.original-once-staged-recovery.v1",
            ) => serde_json::from_value(raw)
                .map(Self::Original)
                .map_err(D::Error::custom),
            Some(
                "droidloom.working-qualification-initramfs-recipe.v1"
                | "droidloom.working-qualification-staged-recovery.v1",
            ) => serde_json::from_value(raw)
                .map(Self::Working)
                .map_err(D::Error::custom),
            _ => Err(D::Error::custom(
                "unknown source-owned normal recovery recipe",
            )),
        }
    }
}
impl RecoveryRecipe {
    pub(crate) fn source_pins(&self) -> Vec<&FilePin> {
        match self {
            Self::Original(v) => v.source_pins(),
            Self::Working(v) => v.source_pins(),
        }
    }
}
pub(crate) fn admit_recovery_recipe(
    input: &FilePin,
    producer: &FilePin,
    materials: &Value,
) -> Result<RecoveryRecipe> {
    // This initial read chooses only the fixed parser. The chosen factory then
    // acquires and fully revalidates the actual held input and all its sources.
    let raw: Value = serde_json::from_slice(&files::read_pin(input, 65536)?)?;
    match raw.get("schema").and_then(Value::as_str) {
        Some("droidloom.original-once-initramfs-recipe.v1") => {
            crate::cold_original_once_initramfs::admit_recovery_recipe(input, producer, materials)
                .map(RecoveryRecipe::Original)
        }
        Some("droidloom.working-qualification-initramfs-recipe.v1") => {
            crate::cold_working_initramfs::admit_recovery_recipe(input, producer, materials)
                .map(RecoveryRecipe::Working)
        }
        _ => Err("unknown normal initramfs recovery source schema".into()),
    }
}
pub(crate) fn stage_recovery_recipe(
    recipe: &RecoveryRecipe,
    build: &Path,
) -> Result<RecoveryRecipe> {
    match recipe {
        RecoveryRecipe::Original(v) => {
            crate::cold_original_once_initramfs::stage_recovery_recipe(v, build)
                .map(RecoveryRecipe::Original)
        }
        RecoveryRecipe::Working(v) => {
            crate::cold_working_initramfs::stage_recovery_recipe(v, build)
                .map(RecoveryRecipe::Working)
        }
    }
}
pub(crate) fn verify_staged(admitted: &RecoveryRecipe, staged: &RecoveryRecipe) -> Result<()> {
    let (input_schema, stage_schema) = match (admitted, staged) {
        (RecoveryRecipe::Original(_), RecoveryRecipe::Original(_)) => (
            "droidloom.original-once-initramfs-recipe.v1",
            "droidloom.original-once-staged-recovery.v1",
        ),
        (RecoveryRecipe::Working(_), RecoveryRecipe::Working(_)) => (
            "droidloom.working-qualification-initramfs-recipe.v1",
            "droidloom.working-qualification-staged-recovery.v1",
        ),
        _ => return Err("normal recovery staging changed its source kind".into()),
    };
    let mut expected = serde_json::to_value(admitted)?;
    ensure(
        expected["schema"] == input_schema,
        "normal recovery source recipe schema differs",
    )?;
    expected["schema"] = json!(stage_schema);
    expected["helper"]["path"] = json!("/build/producer");
    expected["base_intent"]["path"] = json!("/build/recovery/INTENT.json");
    expected["early_configuration"]["path"] = json!("/build/recovery/EARLY.json");
    ensure(
        expected == serde_json::to_value(staged)?,
        "normal recovery private staging differs from its source recipe",
    )
}
pub(crate) fn other_kind_paths(recipe: &RecoveryRecipe) -> [&'static str; 3] {
    match recipe {
        RecoveryRecipe::Original(_) => [
            "/usr/lib/droidloom/qualification/working-recovery",
            "/etc/droidloom/qualification/working-early.json",
            "/scripts/init-top/00-droidloom-working-qualification-recovery",
        ],
        RecoveryRecipe::Working(_) => [
            "/usr/lib/droidloom/qualification/once-recovery",
            "/etc/droidloom/qualification/early.json",
            "/scripts/init-top/00-droidloom-original-once-recovery",
        ],
    }
}
fn reject_other_kind(recipe: &RecoveryRecipe, root: &Path) -> Result<()> {
    let tree = crate::fs::Tree::open(&crate::fs::absolute_string(root)?, 0)?;
    for name in other_kind_paths(recipe) {
        match tree.identity(name) {
            Err(error)
                if error.downcast_ref::<rustix::io::Errno>() == Some(&rustix::io::Errno::NOENT) => {
            }
            _ => return Err("normal recovery image contains another boot kind".into()),
        }
    }
    Ok(())
}

pub(crate) fn install_private_recipe(
    recipe: &RecoveryRecipe,
    producer: &FilePin,
    original: &Value,
) -> Result<Value> {
    // Existing normal roots cannot smuggle a second early entry into the new image.
    reject_other_kind(recipe, Path::new("/"))?;
    match recipe {
        RecoveryRecipe::Original(v) => {
            crate::cold_original_once_initramfs::install_private_recipe(v, producer, original)
        }
        RecoveryRecipe::Working(v) => {
            crate::cold_working_initramfs::install_private_recipe(v, producer, original)
        }
    }
}
pub(crate) fn verify_recovery_image(recipe: &RecoveryRecipe, unpacked: &Path) -> Result<Value> {
    let observed = match recipe {
        RecoveryRecipe::Original(v) => {
            crate::cold_original_once_initramfs::verify_recovery_image(v, unpacked)
        }
        RecoveryRecipe::Working(v) => {
            crate::cold_working_initramfs::verify_recovery_image(v, unpacked)
        }
    }?;
    let roots = [unpacked.to_owned(), unpacked.join("main")]
        .into_iter()
        .filter(|root| root.join("init").is_file())
        .collect::<Vec<_>>();
    ensure(
        roots.len() == 1,
        "normal recovery unpacked root is not unique",
    )?;
    reject_other_kind(recipe, &roots[0])?;
    Ok(observed)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn recipe(working: bool) -> Value {
        use crate::cold_original_once_recovery::contract as original;
        let pin = json!({"path":"/fixed/normal-producer","bytes":10000,"sha256":"a".repeat(64)});
        let mut recovery = json!({
            "schema":"droidloom.original-once-recovery-boot.v1",
            "candidate_id":"b".repeat(64),"helper_bytes":10000,"helper_sha256":"a".repeat(64),
            "kernel_release":original::KERNEL,"kernel_sha256":original::KERNEL_SHA,
            "kernel_config_sha256":original::CONFIG_SHA,"module_relative":original::MODULE_REL,
            "module_bytes":original::MODULE_BYTES,"module_sha256":original::MODULE_SHA,
            "watchdog_seconds":900,"collect_at_boot_seconds":180,"return_at_boot_seconds":600,
            "panic_seconds":10
        });
        if working {
            recovery["schema"] = json!("droidloom.working-qualification-boot.v1");
            recovery["kind"] = json!("working_copy_qualification");
            recovery["first_once_candidate"] = json!("c".repeat(64));
            for key in [
                "watchdog_seconds",
                "collect_at_boot_seconds",
                "return_at_boot_seconds",
            ] {
                recovery.as_object_mut().unwrap().remove(key);
            }
            recovery["schedule"] = serde_json::to_value(
                crate::cold_working_recovery::contract::WorkingSchedule::selected(),
            )
            .unwrap();
        }
        json!({
            "schema":if working {"droidloom.working-qualification-initramfs-recipe.v1"}
                else {"droidloom.original-once-initramfs-recipe.v1"},
            "source_input":pin,"source_producer":pin,"helper":pin,
            "base_intent":pin,"early_configuration":pin,
            "normal_public_release_id":"d".repeat(64),"normal_native_release_id":"e".repeat(64),
            "recovery":recovery
        })
    }
    fn staged(value: &Value, working: bool) -> Value {
        let mut out = value.clone();
        out["schema"] = json!(if working {
            "droidloom.working-qualification-staged-recovery.v1"
        } else {
            "droidloom.original-once-staged-recovery.v1"
        });
        out["helper"]["path"] = json!("/build/producer");
        out["base_intent"]["path"] = json!("/build/recovery/INTENT.json");
        out["early_configuration"]["path"] = json!("/build/recovery/EARLY.json");
        out
    }
    #[test]
    fn normal_recovery_recipe_original_bytes_survive_closed_dispatch() -> Result<()> {
        let input = recipe(false);
        let original: crate::cold_original_once_initramfs::RecoveryRecipe =
            serde_json::from_value(input.clone())?;
        let dispatch: RecoveryRecipe = serde_json::from_value(input)?;
        ensure(
            serde_json::to_vec(&original)? == serde_json::to_vec(&dispatch)?,
            "closed wrapper changed original normal serialization",
        )?;
        assert_eq!(dispatch.source_pins().len(), 4);
        Ok(())
    }
    #[test]
    fn normal_recovery_recipe_staging_rejects_extra_substitutions() -> Result<()> {
        for working in [false, true] {
            let source = recipe(working);
            let admitted: RecoveryRecipe = serde_json::from_value(source.clone())?;
            let expected = staged(&source, working);
            let staged_recipe: RecoveryRecipe = serde_json::from_value(expected.clone())?;
            verify_staged(&admitted, &staged_recipe)?;
            for (outer, inner) in [
                ("helper", "sha256"),
                ("source_input", "path"),
                ("source_producer", "path"),
                ("base_intent", "bytes"),
            ] {
                let mut wrong = expected.clone();
                wrong[outer][inner] = if inner == "bytes" {
                    json!(10001)
                } else {
                    json!("f".repeat(64))
                };
                let changed: RecoveryRecipe = serde_json::from_value(wrong)?;
                assert!(verify_staged(&admitted, &changed).is_err());
            }
        }
        let original: RecoveryRecipe = serde_json::from_value(recipe(false))?;
        let working: RecoveryRecipe = serde_json::from_value(staged(&recipe(true), true))?;
        assert!(verify_staged(&original, &working).is_err());
        Ok(())
    }
    #[test]
    fn normal_recovery_recipe_rejects_unknown_schemas_and_mixed_boot_shapes() {
        for schema in [
            "droidloom.working-qualification-initramfs-recipe.v2",
            "caller-recovery",
            "",
        ] {
            let mut raw = recipe(true);
            raw["schema"] = json!(schema);
            assert!(serde_json::from_value::<RecoveryRecipe>(raw).is_err());
        }
        let mut original = recipe(false);
        original["recovery"]["kind"] = json!("working_copy_qualification");
        assert!(serde_json::from_value::<RecoveryRecipe>(original).is_err());
        let mut working = recipe(true);
        working["recovery"]["watchdog_seconds"] = json!(114505);
        assert!(serde_json::from_value::<RecoveryRecipe>(working).is_err());
    }
}
