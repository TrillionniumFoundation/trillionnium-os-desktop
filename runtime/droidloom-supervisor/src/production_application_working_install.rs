//! Normal replace-capable PackageInstaller sessions on the actual held working
//! pair, before source/PM PLAN capture. Android alone decides signer continuity.
use super::*;
use crate::native_working_install::{self as wire, WorkingInstallRequest, WorkingInstallReply};
use crate::production_selection::early_generation::EarlyApplicationAuthority;
use std::time::Instant;
fn current_main(owner: &EarlyApplicationAuthority<'_>, expected: &crate::main_custody::RuntimeMainCustody,
    end: Instant) -> Result<crate::main_custody::RuntimeMainCustody>
{
    owner.check_request_deadline().map_err(observation_authority_error)?;
    require(owner.request_deadline() == Some(end), "original working installation end differs")?;
    let actual = owner.observe_main_custody(&expected.epoch, end).map_err(observation_authority_error)?;
    require(actual == *expected, "normal working install actual Main or working backing changed")?;
    Ok(actual)
}
pub(crate) fn install_working_originals(owner: &EarlyApplicationAuthority<'_>, request: WorkingInstallRequest,
    payload: File, end: Instant) -> Result<WorkingInstallReply>
{
    request.validate().map_err(external)?;
    let original = wire::application(request.package()).map_err(external)?;
    let before_main = current_main(owner, request.main(), end)?;
    crate::control::apk_payload::validate_production_context(&payload).map_err(external)?;
    original.require_payload(&payload, end).map_err(external)?;
    owner.check_request_deadline().map_err(observation_authority_error)?;
    // This is the maintained -r installer. No uninstall, -k, downgrade, re-sign,
    // source replacement, credential import, or automatic retry exists here.
    let installed = install_early(owner, 0, payload, &original.lengths(), end);
    let after_main = current_main(owner, request.main(), end);
    if matches!(&installed, Err(ApplicationError::RetirementUnproven))
        || matches!(&after_main, Err(ApplicationError::RetirementUnproven)) {
        return Err(ApplicationError::RetirementUnproven);
    }
    let installed = installed?; let after_main = after_main?;
    owner.check_request_deadline().map_err(observation_authority_error)?;
    WorkingInstallReply::from_actual(request, before_main, after_main, &installed).map_err(external)
}
