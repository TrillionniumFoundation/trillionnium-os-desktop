//! Proof emitted only by the authenticated boot-born factory query client.
//! Field visibility deliberately prevents a caller or deserializer from
//! constructing an observed TRACEEXEC event. The factory remains the actual
//! creating thread, ptracer and final waitid owner of every query child.

/// The same direct child at its actual factory-owned PTRACE_EVENT_EXEC stop.
pub(crate) struct FactoryExecStop {
    pid: u32,
    tracer_tid: u32,
    waitid_code: i32,
    waitid_status: i32,
    event_previous_tid: u64,
}
impl FactoryExecStop {
    pub(crate) fn pid(&self) -> u32 { self.pid }
    pub(crate) fn tracer_tid(&self) -> u32 { self.tracer_tid }
    pub(crate) fn waitid_code(&self) -> i32 { self.waitid_code }
    pub(crate) fn waitid_status(&self) -> i32 { self.waitid_status }
    pub(crate) fn event_previous_tid(&self) -> u64 { self.event_previous_tid }
}
