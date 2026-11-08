"""Fresh baseline, all original package bytes, owner, OFD and phase guard.

No Android command is sent by this guard. Original state machines independently
retain their exact account, provider, UI, event and cleanup predicates.
"""


def prepare(*, runtime):
    c = runtime.c
    c.need(type(runtime.private_context) is dict and set(runtime.private_context) == {'phase_lease', 'session'},
           'EXPLICIT_SAME_PROCESS_CASE_AND_PHASE_REQUIRED')
    runtime.session = runtime.private_context['session']
    runtime.phase_lease_ref = runtime.private_context['phase_lease']
    runtime.case_runtime = c.packet_module(runtime.scope, 'search_runtime.py')
    runtime.host_runtime = c.packet_module(runtime.scope, 'app_runtime.py')
    plan = c.packet_module(runtime.scope, 'search_plan.py')
    plan.validate(c, runtime.plan, runtime.view.baseline, runtime.scope)
    runtime.session.verify_runtime(runtime)
    runtime.receipt_witness = c.EvidenceWitness([runtime.scope['phase_plan'], runtime.scope['actual_resolution_receipt'],
        *runtime.scope['installed_helper_receipts'], runtime.plan['lease'], runtime.plan['action_lock']])
    runtime.bound.commands = runtime.host_runtime.PhaseCommands(runtime.bound.commands, runtime)


def full_guard(*, attempted=False, runtime):
    c = runtime.c
    c.need(type(attempted) is bool and runtime.receipt_witness is not None, 'COMPLETE_NEW_SYSTEM_GUARD_REQUIRED')
    runtime.receipt_witness.verify(); runtime.artifacts.verify()
    runtime.session.verify_runtime(runtime)
    phase = runtime.case_runtime.validate_phase(c, runtime.host_runtime, runtime.phase_lease_ref,
        runtime.scope['phase_plan'], runtime.plan)
    c.need(runtime.deadline == phase['deadline_monotonic_ns'] / 1000000000,
           'FLOW_MUST_USE_CURRENT_ABSOLUTE_ORIGINAL_PHASE')
    return {'same_fresh_Main': True, 'same_actual_packages': True,
        'phase_lease': runtime.phase_lease_ref, 'case_owner': phase['owner'],
        'whole_case_action_lock': runtime.plan['action_lock'], 'whole_app_business_accepted': False}
