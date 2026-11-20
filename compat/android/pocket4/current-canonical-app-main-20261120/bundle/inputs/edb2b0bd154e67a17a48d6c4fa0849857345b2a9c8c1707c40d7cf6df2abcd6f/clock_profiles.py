"""Original DeskClock case limits and installed identities, never receipts."""
PACKAGE='com.android.deskclock'
COMPONENT=PACKAGE+'/.DeskClock'
NATIVE='local.pocket4.actions.v2'
CLOCK={'package':PACKAGE,'uid':10063,'version_code':37,'component':COMPONENT,
    'apks':[{'bytes':7597225,'sha256':'433ff501b92a21bb9265c896add220b52bc16fc4124662eaf45310da99243a0d'}],
    'certificate_sha256':'a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc','require_v3':True}
NATIVE_HELPER={'package':NATIVE,'uid':10125,'version_code':2,'component':None,
    'apks':[{'bytes':20847,'sha256':'a5368465d5f6faef3299bf1ba6d6bde268cc8b37c72401c6e668872b24725058'}],
    'certificate_sha256':None,'require_v3':False}
LIMITS={
    'timer15':{'business_seconds':350,'lease_seconds':360,'cleanup_seconds':35,'maximum_UI_actions':20,
        'timer_duration_ms':900000,'maximum_native_launches':2,'maximum_new_alarms':0},
    'expiry06':{'business_seconds':230,'lease_seconds':240,'cleanup_seconds':45,'maximum_UI_actions':12,
        'timer_duration_ms':60000,'maximum_native_launches':2,'maximum_new_alarms':0},
    'alarm04':{'business_seconds':590,'lease_seconds':600,'cleanup_seconds':90,'maximum_UI_actions':24,
        'timer_duration_ms':None,'maximum_native_launches':2,'maximum_new_alarms':1},
}
for _limits in LIMITS.values():
    _limits.update(native_launch_timeout=45,settings_writes=0,permission_writes=0,
        SQL_write_commands=0,provider_write_commands=0,unknown_action_replays=0,
        whole_app_business_accepted=False)
del _limits

# These are the original scalar scope decisions. Current Main, APK, app UID,
# data backing, each launch and every required action must be newly observed.
REQUIRED_GATES={
    'timer15':('create_pause_stable','close_reopen_same_timer','resume_remaining_decreases',
        'reset_full_duration','exact_delete','two_normal_closes','protected_state_preserved'),
    'expiry06':('natural_sixty_second_expiry','active_timer_notification','source_bound_expired_window',
        'native_stop_exact_reset','exact_delete_notification_clear','two_normal_closes',
        'protected_state_preserved'),
    'alarm04':('one_UI_created_owned_alarm','future_labelled_instance','natural_firing',
        'source_bound_notification','exact_instance_alert_window','native_dismiss_effect',
        'normal_close_reopen_time_timezone','exact_delete','task_set_restored','protected_state_preserved'),
}
