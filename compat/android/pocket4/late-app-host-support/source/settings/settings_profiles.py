"""Exact installed Settings, original launcher alias, page routes and three gates."""

SETTINGS = {'package': 'com.android.settings', 'uid': 1000, 'version_code': 37,
    'component': 'com.android.settings/.Settings',
    'apks': [{'bytes': 90336159, 'sha256': 'cb3079368ec4dd3f32da66c8586adca9165ba3a8a24a25255914a969b73517ab'}],
    'certificate_sha256': 'c8a2e9bccf597c2fb6dc66bee293fc13f2fc47ec77bc6b2b0d52c11f51192ab8',
    'require_v3': False}
NATIVE_HELPER = {'package': 'local.pocket4.actions.v2', 'uid': 10125, 'version_code': 2,
    'component': None, 'apks': [{'bytes': 20847, 'sha256': 'a5368465d5f6faef3299bf1ba6d6bde268cc8b37c72401c6e668872b24725058'}],
    'certificate_sha256': None, 'require_v3': False}
HOME = 'com.android.settings/.homepage.SettingsHomepageActivity'
KINDS = ('settings_pages', 'settings_permissions', 'settings_roundtrip')
ROUTES = {
    'system': {'component': 'com.android.settings/.Settings$SystemDashboardActivity', 'titles': ['System']},
    'network': {'component': 'com.android.settings/.Settings$NetworkDashboardActivity', 'titles': ['Network & internet']},
    'display': {'component': 'com.android.settings/.Settings$DisplaySettingsActivity', 'titles': ['Brightness', 'Appearance', 'Screen timeout']},
    'storage': {'component': 'com.android.settings/.Settings$StorageDashboardActivity', 'titles': ['Storage']},
    'applications': {'component': 'com.android.settings/.Settings$AppDashboardActivity', 'titles': ['Apps']},
    'accounts': {'component': 'com.android.settings/.Settings$AccountDashboardActivity', 'titles': ['Passwords & accounts']},
    'privacy': {'component': 'com.android.settings/.Settings$PrivacyDashboardActivity', 'titles': ['Privacy']},
    'special_access': {'component': 'com.android.settings/.Settings$SpecialAccessSettingsActivity', 'titles': ['Special app access']},
    'rotation': {'component': 'com.android.settings/.Settings$SmartAutoRotateSettingsActivity', 'titles': ['Auto-rotate screen', 'Use auto-rotate']},
}
GATES = {
    'settings.pages': 'Verify supported system, network, display, storage and application settings pages.',
    'settings.permissions': 'Verify permission/account interfaces and error handling without granting or changing unrelated state.',
    'settings.roundtrip': 'Change one explicitly selected reversible test setting, verify effect/persistence and restore its original value.',
}
LIMITS = {'business_seconds': 420, 'cleanup_seconds': 60, 'maximum_UI_actions': 4,
    'maximum_native_launches': 2, 'native_launch_timeout': 45, 'maximum_routes': 16,
    'maximum_read_observations_per_wait': 8, 'permission_writes': 0, 'account_operations': 0,
    'package_mutations': 0, 'network_configuration_writes': 0, 'direct_setting_writes': 0,
    'reversible_setting': 'system/accelerometer_rotation', 'shared_UID_is_package_identity': False}

def profiles(kind):
    if kind not in KINDS:
        raise RuntimeError('ONLY_ORIGINAL_SETTINGS_GATES')
    return SETTINGS, NATIVE_HELPER, LIMITS
