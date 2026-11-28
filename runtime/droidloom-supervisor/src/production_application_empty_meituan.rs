//! One fixed normal create-only installation on a live positive EMPTY owner.
use super::*;
use crate::{
    empty_meituan_contract as fixed,
    native_empty_meituan_install::{self as wire, Reply, Request},
    package_inventory_observation::UserZeroPackageInventoryFacts,
    production_selection::early_generation::EarlyApplicationAuthority,
};
use std::time::Instant;

pub(super) fn absence_arguments() -> Result<Vec<CString>> {
    [
        "/system/bin/cmd",
        "package",
        "list",
        "packages",
        "-u",
        "-U",
        "--user",
        "all",
        fixed::PACKAGE,
    ]
    .into_iter()
    .map(|v| CString::new(v).map_err(external))
    .collect()
}
fn current_main(
    owner: &EarlyApplicationAuthority<'_>,
    expected: &crate::main_custody::RuntimeMainCustody,
    end: Instant,
) -> Result<crate::main_custody::RuntimeMainCustody> {
    require(
        owner.request_deadline() == Some(end),
        "EMPTY actual request deadline changed",
    )?;
    let actual = owner
        .observe_main_custody(&expected.epoch, end)
        .map_err(observation_authority_error)?;
    require(
        actual == *expected,
        "EMPTY actual Main or held pair changed",
    )?;
    wire::require_main(&actual).map_err(external)?;
    Ok(actual)
}
fn inventory(
    owner: &EarlyApplicationAuthority<'_>,
    epoch: &RuntimeEpoch,
    end: Instant,
) -> Result<UserZeroPackageInventoryFacts> {
    let actual = read_user_zero_package_inventory(owner, end)?;
    UserZeroPackageInventoryFacts::from_actual(&actual, epoch).map_err(external)
}
pub(crate) fn install_empty_meituan(
    owner: &EarlyApplicationAuthority<'_>,
    request: Request,
    payload: File,
    end: Instant,
) -> Result<Reply> {
    request.validate().map_err(external)?;
    let before = current_main(owner, request.main(), end)?;
    crate::control::apk_payload::validate_production_context(&payload).map_err(external)?;
    wire::official()
        .require_payload(&payload, end)
        .map_err(external)?;
    let before_inventory = inventory(owner, &before.epoch, end)?;
    require(
        !before_inventory.records().contains_key(fixed::PACKAGE),
        "official package is already installed; no replacement or retry",
    )?;
    let absence = factory_query::run(
        owner,
        &ApplicationOperation::EmptyMeituanRetainedAbsence {},
        end,
    )?;
    require(
        absence.output.status.success()
            && absence.output.stdout.is_empty()
            && absence.output.stderr.is_empty()
            && absence.stderr_bytes == 0
            && absence.receipt.successful_retirement(),
        "all-user retained official package absence was not actually observed",
    )?;
    current_main(owner, request.main(), end)?;
    // This calls the actual storage capability, not the request's serialized
    // origin. The consumed claim is never reset after success, failure or an
    // unknown commit. Only this one newly formatted generation is touched.
    owner
        .claim_empty_meituan_installation(end)
        .map_err(observation_authority_error)?;
    let installed = install_create_only_early(owner, payload, &[fixed::APK_BYTES], end);
    let after = current_main(owner, request.main(), end);
    let after_inventory = inventory(owner, &before.epoch, end);
    if matches!(&installed, Err(ApplicationError::RetirementUnproven))
        || matches!(&after, Err(ApplicationError::RetirementUnproven))
        || matches!(&after_inventory, Err(ApplicationError::RetirementUnproven))
    {
        return Err(ApplicationError::RetirementUnproven);
    }
    Reply::from_actual(
        request,
        before,
        after?,
        before_inventory,
        after_inventory?,
        &absence.receipt,
        &installed?,
    )
    .map_err(external)
}
