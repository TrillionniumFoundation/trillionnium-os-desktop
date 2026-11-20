"""Exact historical failure/fence facts, independent of any fresh Main authority."""
PRIOR={'path': '/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261120-apps-r1/inputs/dae3c605fcf326eb00b8f0485dd092ebf9e2dd95464f3982c3f01b8a36342f9a/result.json', 'bytes': 4500, 'sha256': 'dae3c605fcf326eb00b8f0485dd092ebf9e2dd95464f3982c3f01b8a36342f9a'}
FENCE={'path': '/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261120-apps-r1/inputs/6a98cf8d82ead8506afeb1ff831d1e9fd99d1c8e112f5f750c828125dc6debe1/NEVER_EXECUTE_OR_REUSE.json', 'bytes': 661, 'sha256': '6a98cf8d82ead8506afeb1ff831d1e9fd99d1c8e112f5f750c828125dc6debe1'}

def validate(c):
    prior=c.parse(c.read_ref(PRIOR,65536));fence=c.parse(c.read_ref(FENCE,16384))
    c.need(prior['state']=='DOCUMENTS_FLOW_STOPPED' and prior['error']=='ControlError: STALE_FRAME'
        and prior['business_flow_completed'] is False and prior['whole_app_production_ready'] is False
        and prior['pending_effects']=={} and prior['outcome_unknown'] is False
        and prior['ui_actions']==13 and prior['native_launch_calls']==1 and prior['owned_remove_calls']==2
        and prior['owned_task_ids_closed']==[940,939] and prior['source_bound_adopted_tasks']==[940]
        and prior['cleanup']['staged_apk_removed'] is True and prior['cleanup']['errors']==[]
        and prior['cleanup']['package_absent_verified'] is True and prior['cleanup']['package_uninstalled_verified'] is True
        and prior['cleanup']['file_cleanup']['directory_removed_verified'] is True
        and prior['cleanup']['file_cleanup']['fallback_file_unlink'] is True
        and prior['final_guard']=={'epoch_sha256':'48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f',
            'host_pid':3588089,'init_pid':3588093,'init_start_ticks':80797014},'HISTORICAL_SAF10_FAILURE_AND_CLEANUP_CHANGED')
    c.need(fence['state']=='OLD_STAGE_ENTRY_FENCED' and fence['job_id']=='1a1ab190ab3-fc05-4a51'
        and fence['must_never_remove_or_reuse'] is True and fence['original_termination_confirmed'] is False,
        'HISTORICAL_UNKNOWN_STAGE_MUST_REMAIN_FENCED')
    return {'prior_failure_and_known_cleanup':PRIOR,'original_unknown_stage_fence':FENCE,
        'old_failure_preserved':True,'old_stage_termination_not_inferred':True,
        'old_Main_guard_retained_as_history':prior['final_guard'],'old_runtime_authority_transferred':False,
        'old_package_nonce_reused':False,'old_task_ids_reused':False,'historical_business_success':False}

class HistoricalFacts:
    def __init__(self,c):self.c=c
    def verify(self,session,record):
        proof=validate(self.c)
        self.c.need(session.names.RUN not in ('69814e80ea71f485','eeff7aa90e47139a'),
            'NO_HISTORICAL_FIXTURE_NAME_REUSE')
        proof['current_Main_guard']=session.guard()
        proof['fresh_package_and_directory_absence_still_required']=True
        record('historical-failure-and-fence-independent-of-new-authority',proof)
        return proof
