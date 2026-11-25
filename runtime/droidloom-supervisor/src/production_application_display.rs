//! Fixed primary-display density, executed by the original factory owner.
//! The request selects only an integer. Readback, complete child retirement and
//! the same framework epoch are required before reporting the persisted value.
use super::*;
use crate::production_selection::early_generation::EarlyApplicationAuthority;
use std::time::Instant;

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(tag = "display", deny_unknown_fields)]
pub(super) enum DisplayCommand {
    ReadDensity {},
    SetDensity { dpi: u32 },
}
impl DisplayCommand {
    pub(super) fn validate(&self) -> Result<()> {
        if let Self::SetDensity { dpi } = self {
            require(
                (72..=i32::MAX as u32).contains(dpi),
                "display density is outside the stock WindowManager range",
            )?;
        }
        Ok(())
    }
    pub(super) fn arguments(&self) -> Result<Vec<CString>> {
        self.validate()?;
        let mut args = vec!["/system/bin/cmd".to_owned(), "window".into(), "density".into()];
        if let Self::SetDensity { dpi } = self {
            args.push(dpi.to_string());
        }
        // -d is the fixed display ID; stock -u denotes a display unique ID,
        // not an Android user. The normal command persists for USER_CURRENT.
        args.extend(["-d".into(), "0".into()]);
        args.into_iter().map(|v| CString::new(v).map_err(external)).collect()
    }
}
fn namespace_error(error: crate::production_namespace::NamespaceError) -> ApplicationError {
    match error {
        crate::production_namespace::NamespaceError::RetirementUnproven =>
            ApplicationError::RetirementUnproven,
        value => external(value),
    }
}
fn observed_density(bytes: &[u8]) -> Result<u32> {
    require(!bytes.is_empty() && bytes.len() <= 4096, "density readback size differs")?;
    let text = std::str::from_utf8(bytes).map_err(external)?;
    let mut physical = None;
    let mut forced = None;
    for line in text.lines() {
        let (slot, value) = if let Some(value) = line.strip_prefix("Physical density: ") {
            (&mut physical, value)
        } else if let Some(value) = line.strip_prefix("Override density: ") {
            (&mut forced, value)
        } else {
            return Err(reject("WindowManager returned an unexpected density line"));
        };
        require(slot.is_none(), "duplicate density readback field")?;
        let dpi = value.parse::<u32>().map_err(external)?;
        require(
            dpi.to_string() == value && (72..=i32::MAX as u32).contains(&dpi),
            "density readback is not a canonical stock value",
        )?;
        *slot = Some(dpi);
    }
    let physical = physical.ok_or_else(|| reject("physical display density is absent"))?;
    Ok(forced.unwrap_or(physical))
}
fn execute(
    authority: &EarlyApplicationAuthority<'_>,
    command: DisplayCommand,
    deadline: Instant,
) -> Result<Vec<u8>> {
    command.validate()?;
    authority.ready().map_err(namespace_error)?;
    let operation = ApplicationOperation::Display { value: command.clone() };
    let result = workflow::finish_effect(
        factory_query::run(authority, &operation, deadline),
        || authority.ready().map_err(namespace_error),
        deadline,
    )?;
    require(
        result.output.status.success() && result.receipt.successful_retirement(),
        "fixed density command did not exit and retire normally",
    )?;
    require(
        result.output.stderr.is_empty(),
        "WindowManager reported a density command error",
    )?;
    eprintln!("droidloom-display-density {}", serde_json::to_string(
        &serde_json::json!({"command":command,"receipt":result.receipt})
    ).map_err(external)?);
    Ok(result.output.stdout)
}
pub(crate) fn set_density_early(
    authority: &EarlyApplicationAuthority<'_>,
    dpi: u32,
    overall_deadline: Instant,
) -> Result<u32> {
    DisplayCommand::SetDensity { dpi }.validate()?;
    let deadline = (Instant::now() + QUERY_LIMIT).min(overall_deadline);
    let framework = authority.observe_framework().map_err(namespace_error)?;
    let epoch = authority.epoch(&framework).map_err(namespace_error)?;
    let output = execute(authority, DisplayCommand::SetDensity { dpi }, deadline)?;
    require(
        std::str::from_utf8(&output).map_err(external)?.trim().is_empty(),
        "WindowManager returned unexpected density mutation output",
    )?;
    let readback = observed_density(&execute(authority, DisplayCommand::ReadDensity {}, deadline)?)?;
    require(readback == dpi, "persisted display density differs from the request")?;
    require(
        authority.epoch(&framework).map_err(namespace_error)? == epoch,
        "density operation crossed a framework epoch",
    )?;
    require(Instant::now() < deadline, "density readback exceeded its deadline")?;
    Ok(readback)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn density_commands_bind_only_primary_display_and_stock_integer_range() {
        let read = (DisplayCommand::ReadDensity {}).arguments().unwrap();
        assert_eq!(read.iter().map(|v| v.to_str().unwrap()).collect::<Vec<_>>(),
                   ["/system/bin/cmd","window","density","-d","0"]);
        for dpi in [72,175,420,i32::MAX as u32] {
            let write = DisplayCommand::SetDensity { dpi }.arguments().unwrap();
            assert_eq!(write.iter().map(|v| v.to_str().unwrap()).collect::<Vec<_>>(),
                       ["/system/bin/cmd","window","density",&dpi.to_string(),"-d","0"]);
        }
        for dpi in [0,71,i32::MAX as u32+1,u32::MAX] {
            assert!(DisplayCommand::SetDensity { dpi }.validate().is_err());
        }
        for body in [
            r#"{"display":"SetDensity","dpi":175,"user":10}"#,
            r#"{"display":"SetDensity","dpi":175,"binary":"/system/bin/sh"}"#,
            r#"{"display":"ReadDensity","display_id":1}"#,
            r#"{"display":"SetDensity","dpi":"175;id"}"#,
        ] {
            assert!(serde_json::from_str::<DisplayCommand>(body).is_err(), "{body}");
        }
        let request = ApplicationOperation::Display { value: DisplayCommand::ReadDensity {} };
        assert_eq!(request.domain(), OperationDomain::DisplayControl);
        assert_eq!(request.binary(), c"cmd");
        assert_eq!(request.descriptor_count(), 15);
        assert!(!request.uses_app_process());
    }
    #[test]
    fn density_readback_requires_complete_unique_canonical_actual_values() {
        assert_eq!(observed_density(b"Physical density: 420\n").unwrap(), 420);
        assert_eq!(observed_density(b"Physical density: 420\nOverride density: 175\n").unwrap(), 175);
        for body in [
            "", "Override density: 175\n", "Physical density: 0\n",
            "Physical density: 0420\n", "Physical density: 420\nPhysical density: 420\n",
            "Physical density: 420\nOverride density: 175\nOverride density: 175\n",
            "Physical density: 420\nError: Permission denied\n", "Can't find service: window\n",
            "Physical density: 420 \n", "Physical density: 420\n\n",
        ] {
            assert!(observed_density(body.as_bytes()).is_err(), "{body:?}");
        }
    }
}
