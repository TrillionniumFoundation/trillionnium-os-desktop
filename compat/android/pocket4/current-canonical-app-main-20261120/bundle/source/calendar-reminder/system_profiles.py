"""Exact original reminder22 package and lease contract; no historical execution credit."""
CALENDAR = {'package': 'com.android.calendar', 'uid': 10061, 'version_code': 37, 'component': 'com.android.calendar/.AllInOneActivity', 'apks': [{'bytes': 2520846, 'sha256': '726241395b485794badd1a1fdcef4298ebb284f67826d73a7e2648f2b7a5382e'}], 'certificate_sha256': 'a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc', 'require_v3': False}
CALENDAR_PROVIDER = {'package': 'com.android.providers.calendar', 'uid': 10017, 'version_code': 37, 'component': None, 'apks': [{'bytes': 336615, 'sha256': '1ae37944b4f5f24d8d7bc849c76bd80c678d19cc3f5647ccaebd1254d8508744'}], 'certificate_sha256': 'a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc', 'require_v3': False}
NATIVE_HELPER = {'package': 'local.pocket4.actions.v2', 'uid': 10125, 'version_code': 2, 'component': None, 'apks': [{'bytes': 20847, 'sha256': 'a5368465d5f6faef3299bf1ba6d6bde268cc8b37c72401c6e668872b24725058'}], 'certificate_sha256': None, 'require_v3': False}
CALENDAR_INSTALL = {'path': '/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261120-apps-r1/inputs/ad31776194c0fb66dd4bed6a77bbbec3409782317912812ee965705d2d4053c2/result.json', 'bytes': 10606, 'sha256': 'ad31776194c0fb66dd4bed6a77bbbec3409782317912812ee965705d2d4053c2'}
TASK_PROOF = {'path': '/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261120-apps-r1/inputs/9cb008b7050d3bb0b8da2221140c02b39ebde973833b5ee24039932e266e90a5/task-option-proof.json', 'bytes': 17797, 'sha256': '9cb008b7050d3bb0b8da2221140c02b39ebde973833b5ee24039932e266e90a5'}
ATOMIC_REVIEW = {'path': '/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261120-apps-r1/inputs/1d66de839c05c11983196764d44c518175bc10481cff754b850d6034c8533796/atomic-delete-review.json', 'bytes': 4133, 'sha256': '1d66de839c05c11983196764d44c518175bc10481cff754b850d6034c8533796'}

CALENDAR_LIMITS = {'business_seconds': 480, 'cleanup_seconds': 90,
    'maximum_UI_actions': 24, 'reserved_cleanup_actions': 4, 'maximum_driver_decisions': 24,
    'maximum_native_launches': 2, 'native_launch_timeout': 45,
    'maximum_calendars_created': 1, 'maximum_events_created': 1,
    'maximum_empty_calendar_deletes': 1, 'account_mutations': 0, 'permission_writes': 0,
    'package_mutations': 0, 'provider_reminder_insert_commands': 0,
    'maximum_host_cpu_percent': 50, 'host_memory_max_bytes': 536870912,
    'natural_due_readback_grace_ms': 60000, 'desktop_or_audio_qualified': False}

def profiles(kind):
    if kind != 'calendar_reminder':
        raise RuntimeError('ONLY_ORIGINAL_CALENDAR_REMINDER22')
    return CALENDAR, CALENDAR_PROVIDER, NATIVE_HELPER, CALENDAR_LIMITS
