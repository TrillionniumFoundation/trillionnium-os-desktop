"""Existing case identities and limits; these constants are never receipts."""

CLOCK = {'package': 'com.android.deskclock', 'uid': 10063, 'version_code': 37,
    'component': 'com.android.deskclock/.DeskClock',
    'apks': [{'bytes': 7597225, 'sha256': '433ff501b92a21bb9265c896add220b52bc16fc4124662eaf45310da99243a0d'}],
    'certificate_sha256': 'a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc',
    'require_v3': True}
CLOCK_HELPER = {'package': 'local.pocket4.actions.v2', 'uid': 10125, 'version_code': None,
    'component': None, 'apks': [{'sha256': 'a5368465d5f6faef3299bf1ba6d6bde268cc8b37c72401c6e668872b24725058'}],
    'certificate_sha256': None, 'require_v3': False}
IHG = {'package': 'com.ihg.apps.android', 'uid': 10137, 'version_code': 50023496,
    'component': 'com.ihg.apps.android/.activity.MainActivity',
    'apks': [{'bytes': 47668450, 'sha256': '1b2c410b16e9f8e69fcc53d97138d7e8c3e7a1e500abb5372f3700d2a950af4f'}],
    'certificate_sha256': None, 'require_v3': False}
CLOCK_LIMITS = {'business_seconds': 350, 'lease_seconds': 360, 'cleanup_seconds': 35,
    'maximum_UI_actions': 20, 'timer_duration_ms': 900000, 'maximum_native_launches': 2,
    'native_launch_timeout': 45, 'permission_writes': 0, 'settings_writes': 0,
    'alarm_writes': 0, 'scheduler_cancellation_verified': False}
IHG_LIMITS = {'phase_seconds': {'launch': 175, 'inspect': 175, 'cleanup': 115},
    'coordinator_seconds': 600, 'maximum_native_launches': 1, 'native_launch_timeout': 70,
    'maximum_clicks': 2, 'maximum_text_actions': 1, 'fixed_public_input': 'London',
    'maximum_readiness_sequences': 8, 'helper_operation_nonces': 39,
    'screenshots': 0, 'audio_actions': 0, 'permission_writes': 0, 'settings_writes': 0}


def helper_expected(common, build, uid):
    common.need(type(uid) is int and 10000 <= uid < 100000 and uid not in
        (10137,10121,10129,10117,10125,10164,10165,10166,10169,10170,10175,10184,10190,10196,10153,10156,10158),
        'NEW_FINAL_HELPER_UID_REQUIRED')
    return {'package': 'org.droidloom.qa.ihg.finalmain.r1', 'uid': uid, 'version_code': 1, 'component': None,
        'apks': [{'bytes': build['APK']['bytes'], 'sha256': build['APK']['sha256']}],
        'certificate_sha256': build['signer_certificate_sha256'], 'require_v3': True}
