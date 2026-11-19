"""Run the migrated original 32 baseline and 45 public-input host controls.

Every production parser and Session constructor is loaded from the actual new
generated source packet. Fixtures remain synthetic; no Main/Android/UI call.
"""


def run_controls(common, source):
    result = {'schema': 'pocket4-final-ihg-generated-helper-controls-v1',
        'all_passed': False, 'original_baseline_controls': 32, 'original_input_controls': 45,
        'Android_commands': 0, 'UI_actions': 0, 'processes_spawned': 0,
        'Java_runtime_executed': False, 'whole_app_business_accepted': False}
    reports = {}
    for name, count in (('ihg_check_baseline.py', 32), ('ihg_check_input.py', 45)):
        checker = common.module(source['files'][name], 'actual_generated_' + name[:-3])
        report = checker.run_controls()
        common.need(report['all_passed'] is True and report['count'] == count
            and len(report['cases']) == count and all(row['passed'] is True for row in report['cases'])
            and report['production_contract_sha256'] == source['files']['qa_contract.py']['sha256']
            and report['production_adapter_sha256'] == source['files']['ihg_session.py']['sha256']
            and report['Android_commands'] == report['UI_actions'] == 0,
            'MIGRATED_ORIGINAL_HELPER_CONTROLS_DID_NOT_PASS_ACTUAL_SOURCES')
        reports[name] = report
    first = reports['ihg_check_baseline.py']
    common.need(first['host_recorder_manifest_sha256'] == common.SUPPORT_REF['sha256'] and
        first['main_baseline_schema'] == 'pocket4-final-business-baseline-v1' and
        first['main_epoch_sha256'] == source['framework_epoch_sha256'] and
        first['main_baseline_sha256'] == source['baseline']['sha256'] and
        first['main_baseline_qualification_sha256'] == source['qualification']['sha256'] and
        reports['ihg_check_input.py']['fixed_public_value'] == 'London' and
        reports['ihg_check_input.py']['protocol'] == 'pocket4-owned-ihg-qa-final-main-v1',
        'ACTUAL_NEW_TYPED_SCOPE_OR_PUBLIC_INPUT_CONTROL_BINDING_CHANGED')
    result.update(all_passed=True, reports=reports, count=77)
    return result
