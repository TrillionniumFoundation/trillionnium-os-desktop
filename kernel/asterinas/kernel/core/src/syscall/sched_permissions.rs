// SPDX-License-Identifier: MPL-2.0

//! Resource-limit checks occur under administration, never under the policy spinlock.

use super::sched_get_priority_max::rt_to_static;
use crate::{
    prelude::*,
    process::{Process, ResourceType, credentials::capabilities::CapSet},
    sched::{LinuxSchedPolicy, Nice, SchedAdministration, SchedPolicy},
    security::lsm::hooks as lsm_hooks,
};

pub(super) fn nice_rlimit(nice: Nice) -> u64 {
    (20 - i32::from(nice.value().get())) as u64
}

pub(super) fn require_sys_nice(target: &Process, ctx: &Context) -> Result<()> {
    lsm_hooks::on_capable(lsm_hooks::CapableContext::new(
        target.user_ns().lock().as_ref(),
        ctx.posix_thread,
        CapSet::SYS_NICE,
    ))
}

pub(super) fn set_checked_policy(
    admin: &mut SchedAdministration<'_>,
    policy: SchedPolicy,
    linux_policy: LinuxSchedPolicy,
    target: &Process,
    ctx: &Context,
) -> Result<()> {
    // These copies release the policy spinlock before any credential/LSM work.
    let old = admin.policy();
    let old_linux = admin.user_policy();
    let old_nice = admin.nice();
    let limits = target.resource_limits();
    let rt_limit = limits.get_rlimit(ResourceType::RLIMIT_RTPRIO).get_cur();
    let nice_limit = limits.get_rlimit(ResourceType::RLIMIT_NICE).get_cur();
    let needs_capability = match policy {
        SchedPolicy::RealTime { rt_prio, .. } => {
            let old_priority = match old {
                SchedPolicy::RealTime { rt_prio, .. } => rt_to_static(rt_prio),
                _ => 0,
            };
            let priority = rt_to_static(rt_prio);
            (linux_policy != old_linux && rt_limit == 0)
                || (priority > old_priority && u64::from(priority) > rt_limit)
        }
        SchedPolicy::Fair(nice) if linux_policy != LinuxSchedPolicy::Idle => {
            nice < old_nice && nice_rlimit(nice) > nice_limit
        }
        SchedPolicy::Fair(_) => false,
        SchedPolicy::Stop | SchedPolicy::Idle => {
            return_errno_with_message!(Errno::EPERM, "kernel-only scheduling policy");
        }
    } || (old_linux == LinuxSchedPolicy::Idle
        && linux_policy != LinuxSchedPolicy::Idle
        && nice_rlimit(old_nice) > nice_limit);
    if needs_capability {
        require_sys_nice(target, ctx)?;
    }
    if linux_policy == LinuxSchedPolicy::Idle {
        admin.set_user_idle();
    } else {
        admin.set_policy(policy);
    }
    Ok(())
}
