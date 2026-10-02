//! Exercise the public supervisor contract as a downstream product integration.

use hepta_browserd::{
    BrowserdRuntimeSupervisor, CrashTransition, DispatchCompletion, ProductRuntimeError,
    RestartPolicy, RuntimeGeneration, RuntimeState,
};

#[test]
fn downstream_caller_can_configure_construct_and_recover_supervisor() {
    let policy = RestartPolicy::new(2).expect("bounded restart policy");
    let mut runtime = BrowserdRuntimeSupervisor::start(Ok::<_, ProductRuntimeError>, policy)
        .expect("construct runtime through public API");
    let original = runtime.semantic_reference(7);
    let CrashTransition {
        previous,
        current,
        consecutive_crashes,
        replay_blocked,
    } = runtime.content_process_crashed().expect("record crash");
    assert_eq!(previous, RuntimeGeneration::INITIAL);
    assert_eq!(current.get(), 2);
    assert_eq!(consecutive_crashes, 1);
    assert!(!replay_blocked);
    assert_eq!(runtime.state(), RuntimeState::NeedsReconstruction);
    assert_eq!(runtime.reconstruct(), Ok(current));
    assert_eq!(
        runtime.dispatch(original, |_| DispatchCompletion::Completed(())),
        Err(ProductRuntimeError::StaleGeneration)
    );
    let reference = runtime.semantic_reference(8);
    assert_eq!(
        runtime.dispatch(reference, |actor| DispatchCompletion::Completed(*actor)),
        Ok(current)
    );
}
