"""Exact CP3A Settings pages, read from the selected APK manifest/resources.

This profile authorizes navigation and observation only. It does not authorize
a setting write, permission grant, account action, purchase or message.
"""
PACKAGE = 'com.android.settings'
TARGET = {
    'package': PACKAGE, 'uid': 1000, 'version_code': 37,
    'component': PACKAGE + '/.Settings',
    'apks': [{'bytes': 91609273, 'sha256': 'c2d4c45348dd45483f0893c6236ffb29322a52d2db61f83936be1508bd03a090'}],
    'certificate_sha256': 'c8a2e9bccf597c2fb6dc66bee293fc13f2fc47ec77bc6b2b0d52c11f51192ab8',
    'require_v3': False,
}
HELPER = {
    'package': 'local.pocket4.actions.v2', 'uid': 10125, 'version_code': 2,
    'component': None,
    'apks': [{'bytes': 20847, 'sha256': 'a5368465d5f6faef3299bf1ba6d6bde268cc8b37c72401c6e668872b24725058'}],
    'certificate_sha256': None, 'require_v3': False,
}
HOME_ACTIVITY = PACKAGE + '.homepage.SettingsHomepageActivity'
PAGES = (
    {'name': 'system', 'component': PACKAGE + '/.Settings$SystemDashboardActivity',
     'activity': PACKAGE + '.Settings$SystemDashboardActivity',
     'titles': ['System', '系统', '系統'], 'resource': 'string/header_category_system'},
    {'name': 'network', 'component': PACKAGE + '/.Settings$NetworkDashboardActivity',
     'activity': PACKAGE + '.Settings$NetworkDashboardActivity',
     'titles': ['Network & internet', 'Network and Internet', 'Network and internet', '网络和互联网', '網絡和互聯網', '網路與網際網路'],
     'resource': 'string/network_dashboard_title'},
    {'name': 'display', 'component': PACKAGE + '/.Settings$DisplaySettingsActivity',
     'activity': PACKAGE + '.Settings$DisplaySettingsActivity',
     'titles': ['Display', '显示', '顯示'], 'resource': 'string/display_settings'},
    {'name': 'storage', 'component': PACKAGE + '/.Settings$StorageDashboardActivity',
     'activity': PACKAGE + '.Settings$StorageDashboardActivity',
     'titles': ['Storage', '存储空间', '儲存空間'], 'resource': 'string/storage_settings'},
    {'name': 'applications', 'component': PACKAGE + '/.Settings$ManageApplicationsActivity',
     'activity': PACKAGE + '.Settings$ManageApplicationsActivity',
     'titles': ['App info', '应用信息', '應用程式資料', '應用程式資訊'], 'resource': 'string/applications_settings'},
)
HOME_TITLES = ('Settings', '设置', '設定')
LIMITS = {
    'business_seconds': 600, 'cleanup_seconds': 120,
    'maximum_native_launches': 2, 'maximum_page_routes': 5,
    'maximum_observations': 7, 'maximum_task_removals': 2,
    'CPU_quota_percent': 200, 'memory_max_bytes': 2147483648,
    'swap_max_bytes': 0, 'pids_max': 64,
    'setting_writes': 0, 'permission_writes': 0, 'account_writes': 0,
    'package_writes': 0, 'provider_writes': 0,
}
ORIGINAL_GATES = ('settings.pages', 'settings.roundtrip', 'settings.permissions')
COMPLETABLE_GATE = 'settings.pages'
REMAINING_GATES = ('settings.roundtrip', 'settings.permissions', 'identity', 'lifecycle',
                   'stability', 'data_permissions', 'release_scope', 'ui_observation')


def route_argv(task, page):
    if type(task) is not int or task <= 0 or page not in PAGES:
        raise RuntimeError('EXACT_OBSERVED_TASK_AND_FIXED_SETTINGS_PAGE_REQUIRED')
    # All five components are exported by this exact selected APK. A component
    # route avoids speculative action resolution (the System page has no
    # android.settings.SYSTEM_SETTINGS intent filter in this APK).
    return ['/system/bin/am', 'start-activity', '-W', '--user', '0', '--display', '0',
            '--task', str(task), '--activity-clear-top', '-n', page['component']]
