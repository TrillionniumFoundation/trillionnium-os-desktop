"""New IHG guard; full helper/source chain, original Main and phase limits."""


def prepare(*, runtime):
    runtime.case_runtime = runtime.c.packet_module(runtime.scope, 'app_runtime.py')
    runtime.case_runtime.prepare(runtime)
    runtime.c.need(runtime.plan['kind'] == 'ihg_london' and runtime.plan['protected_before'] is None
                   and runtime.plan['action_lock'] is None,
                   'EXACT_NEW_IHG_PUBLIC_INPUT_CASE_REQUIRED')
    qa = runtime.c.packet_module(runtime.scope, 'qa_contract.py')
    runtime.c.need(qa.SELF == 'org.droidloom.qa.ihg.finalmain.r1'
        and qa.MAIN_BASELINE_SCHEMA == runtime.view.baseline.value['schema']
        and qa.MAIN_EPOCH == runtime.scope['framework_epoch_sha256']
        and qa.MAIN_BASELINE_SHA == runtime.scope['business_baseline']['sha256']
        and qa.MAIN_BASELINE_QUALIFICATION_SHA == runtime.scope['business_qualification']['sha256'],
        'ACTUAL_NEW_MAIN_HELPER_GENERATION_REQUIRED')


def full_guard(*, attempted=False, runtime):
    phase = runtime.case_runtime.full(runtime, attempted)
    artifacts = getattr(runtime, 'commercial_artifacts', None)
    if artifacts is not None:
        artifacts.verify_held()
    return phase


def existing_ui_guard(*, attempted=False, entry_context):
    # IHG's preserved owned instrumentation uses BoundArun directly. It never
    # delegates actions to the generic UI client or takes screenshots.
    raise RuntimeError('IHG_PUBLIC_CASE_DOES_NOT_AUTHORIZE_GENERIC_UI_ENTRY')
