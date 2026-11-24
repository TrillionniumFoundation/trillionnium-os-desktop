//! Package hooks preserve the original resource owner's authority through native stop.
//! Only the fixed supervisor RPC can construct the live and terminal witnesses.
use super::Result;
use droidloom_supervisor::{
    control::package::{
        LivePackageRetirement, NativePackageRetirement, PackageOperation, retire_for_package,
    },
    production_configuration::PackageConfigurationLock,
};
use std::time::{Duration, Instant};

pub(super) fn retire(lock: &PackageConfigurationLock, remove: bool) -> Result<()> {
    let mut owner = OriginalOwner {
        lock,
        deadline: Instant::now() + Duration::from_secs(120),
    };
    complete(&mut owner, operation(remove))
}

fn operation(remove: bool) -> PackageOperation {
    if remove {
        PackageOperation::Remove
    } else {
        PackageOperation::Upgrade
    }
}

// Private sequencing boundary: the production implementation carries the opaque
// supervisor types, never a caller-supplied PID, JSON receipt or success boolean.
trait Retirement {
    type Live;
    type Terminal;

    fn retire_resources(&mut self, operation: PackageOperation) -> Result<Self::Live>;
    fn revalidate_resources(&mut self, live: &Self::Live) -> Result<()>;
    fn stop_native_units(&mut self, live: &Self::Live) -> Result<()>;
    fn verify_native_stop(&mut self, live: Self::Live) -> Result<Self::Terminal>;
    fn revalidate_retirement(&mut self, terminal: &Self::Terminal) -> Result<()>;
}

fn complete(owner: &mut impl Retirement, operation: PackageOperation) -> Result<()> {
    let live = owner.retire_resources(operation)?;
    owner.revalidate_resources(&live)?;
    owner.stop_native_units(&live)?;
    let terminal = owner.verify_native_stop(live)?;
    owner.revalidate_retirement(&terminal)
}

struct OriginalOwner<'a> {
    lock: &'a PackageConfigurationLock,
    deadline: Instant,
}

impl<'a> Retirement for OriginalOwner<'a> {
    type Live = LivePackageRetirement<'a>;
    type Terminal = NativePackageRetirement<'a>;

    fn retire_resources(&mut self, operation: PackageOperation) -> Result<Self::Live> {
        Ok(retire_for_package(self.lock, operation)?)
    }

    fn revalidate_resources(&mut self, live: &Self::Live) -> Result<()> {
        Ok(live.revalidate()?)
    }

    fn stop_native_units(&mut self, live: &Self::Live) -> Result<()> {
        super::stop_native_units(self.deadline, Some(live))
    }

    fn verify_native_stop(&mut self, live: Self::Live) -> Result<Self::Terminal> {
        Ok(live.complete_native_stop()?)
    }

    fn revalidate_retirement(&mut self, terminal: &Self::Terminal) -> Result<()> {
        Ok(terminal.revalidate()?)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[derive(Clone, Copy, Debug, Eq, PartialEq)]
    enum Step {
        Resources,
        LiveOwner,
        NativeStop,
        OriginalExit,
        TerminalProof,
    }

    const STEPS: [Step; 5] = [
        Step::Resources,
        Step::LiveOwner,
        Step::NativeStop,
        Step::OriginalExit,
        Step::TerminalProof,
    ];

    // These model tokens exercise hook ordering only. They cannot construct or
    // replace the supervisor's original-owner kernel witnesses.
    struct Resources;
    struct Terminal;

    #[derive(Default)]
    struct ObservedOwner {
        trace: Vec<Step>,
        fail: Option<Step>,
        commit_on_resource_failure: bool,
        fence: bool,
        stop_requested: bool,
        operation: Option<PackageOperation>,
    }

    impl ObservedOwner {
        fn observe(&mut self, step: Step) -> Result<()> {
            self.trace.push(step);
            if self.fail == Some(step) {
                return Err(format!("{step:?} refused").into());
            }
            Ok(())
        }
    }

    impl Retirement for ObservedOwner {
        type Live = Resources;
        type Terminal = Terminal;

        fn retire_resources(&mut self, operation: PackageOperation) -> Result<Self::Live> {
            self.operation = Some(operation);
            if self.fail != Some(Step::Resources) || self.commit_on_resource_failure {
                self.fence = true;
            }
            self.observe(Step::Resources)?;
            Ok(Resources)
        }

        fn revalidate_resources(&mut self, _: &Self::Live) -> Result<()> {
            self.observe(Step::LiveOwner)
        }

        fn stop_native_units(&mut self, _: &Self::Live) -> Result<()> {
            self.stop_requested = true;
            self.observe(Step::NativeStop)
        }

        fn verify_native_stop(&mut self, _: Self::Live) -> Result<Self::Terminal> {
            self.observe(Step::OriginalExit)?;
            Ok(Terminal)
        }

        fn revalidate_retirement(&mut self, _: &Self::Terminal) -> Result<()> {
            self.observe(Step::TerminalProof)
        }
    }

    #[test]
    fn upgrade_and_removal_require_resource_retirement_and_original_native_exit() {
        for remove in [false, true] {
            let mut owner = ObservedOwner::default();
            complete(&mut owner, operation(remove)).unwrap();
            assert_eq!(owner.trace, STEPS);
            assert!(owner.stop_requested);
            assert!(owner.fence);
            assert!(matches!(
                (remove, owner.operation),
                (false, Some(PackageOperation::Upgrade)) | (true, Some(PackageOperation::Remove))
            ));
        }
    }

    #[test]
    fn absent_resource_owner_authority_never_reaches_native_stop() {
        let mut owner = ObservedOwner {
            fail: Some(Step::Resources),
            ..ObservedOwner::default()
        };
        assert!(complete(&mut owner, PackageOperation::Upgrade).is_err());
        assert_eq!(owner.trace, [Step::Resources]);
        assert!(!owner.stop_requested);
        assert!(!owner.fence);
    }

    #[test]
    fn ambiguous_resource_commit_retains_fence_without_attempting_stop() {
        let mut owner = ObservedOwner {
            fail: Some(Step::Resources),
            commit_on_resource_failure: true,
            ..ObservedOwner::default()
        };
        assert!(complete(&mut owner, PackageOperation::Remove).is_err());
        assert_eq!(owner.trace, [Step::Resources]);
        assert!(!owner.stop_requested);
        assert!(owner.fence);
    }

    #[test]
    fn every_failed_revalidation_stops_the_sequence_and_preserves_the_fence() {
        for (index, step) in STEPS.into_iter().enumerate().skip(1) {
            let mut owner = ObservedOwner {
                fail: Some(step),
                ..ObservedOwner::default()
            };
            assert!(complete(&mut owner, PackageOperation::Upgrade).is_err());
            assert_eq!(owner.trace, STEPS[..=index]);
            assert_eq!(owner.stop_requested, index >= 2);
            assert!(owner.fence);
        }
    }
}
