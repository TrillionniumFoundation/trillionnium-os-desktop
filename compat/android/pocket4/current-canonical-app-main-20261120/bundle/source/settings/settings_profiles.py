"""Exact CP3A Settings pages and one explicitly selected reversible setting.

The additional component/label observations are bound to the same selected APK.
Only user 0 system/time_12_24 may be changed and restored. Permission/account
interfaces remain read-only; a new source-pinned plan is mandatory.
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
DATE_PAGE = {
    'name': 'date_time', 'component': PACKAGE + '/.Settings$DateTimeSettingsActivity',
    'activity': PACKAGE + '.Settings$DateTimeSettingsActivity',
    'titles': ['Date & time', 'Date and time', '日期和时间', '日期和時間'],
    'resource': 'string/date_and_time',
}
PERMISSION_PAGES = (
    {'name': 'special_access', 'component': PACKAGE + '/.Settings$SpecialAccessSettingsActivity',
     'activity': PACKAGE + '.Settings$SpecialAccessSettingsActivity',
     'titles': ['Special app access', '特殊应用权限', '特別應用程式權限', '特殊應用程式存取權'],
     'resource': 'string/special_access'},
    {'name': 'accounts', 'component': PACKAGE + '/.Settings$AccountDashboardActivity',
     'activity': PACKAGE + '.Settings$AccountDashboardActivity',
     'titles': ['Passwords & accounts', 'Passwords and accounts', '密码和账号', '密碼和帳戶', '密碼與帳戶'],
     'resource': 'string/account_dashboard_title'},
)
TIME_FORMAT_TITLES = ('Use 24-hour format', '使用 24 小时制', '使用 24 小時格式')
LOCALE_FORMAT_TITLES = ('Use locale default', '使用默认语言区域', '使用地區設定預設值')
ALL_PAGES = PAGES + (DATE_PAGE,) + PERMISSION_PAGES
# Ordered routes across two distinct native launches. Observations after each
# write are separate from routes; no arbitrary exported activity is accepted.
ROUTE_SEQUENCE = PAGES + (DATE_PAGE,) + PERMISSION_PAGES + (DATE_PAGE, PAGES[0], DATE_PAGE)
BUSINESS_CONTRACT = {
    'schema': 'pocket4-settings-business-contract-v2',
    'selected_reversible_setting': {'user': 0, 'namespace': 'system', 'key': 'time_12_24',
        'accepted_original_values': [None, '12', '24'], 'maximum_writes': 2,
        'persistence_boundary': 'separate-owned-task-close-and-native-reopen',
        'restore_absent_key_by_delete': True},
    'permission_account_scope': 'readonly-owned-pages-and-service-readback',
    'permission_writes': 0, 'account_writes': 0,
}
SETTINGS_READ = ['/system/bin/settings', '--user', '0', 'list', 'system']
PERMISSION_CHECK = ['/system/bin/dumpsys', 'package', 'check-permission',
                    'android.permission.CAMERA', PACKAGE, '0']
PERMISSION_ERROR = ['/system/bin/dumpsys', 'package', 'check-permission']
ACCOUNT_READ = ['/system/bin/dumpsys', 'account']
LIMITS = {
    'business_seconds': 600, 'cleanup_seconds': 120,
    'maximum_native_launches': 2, 'maximum_page_routes': 11,
    'maximum_observations': 13, 'maximum_task_removals': 2,
    'CPU_quota_percent': 200, 'memory_max_bytes': 2147483648,
    'swap_max_bytes': 0, 'pids_max': 64,
    'setting_writes': 2, 'permission_writes': 0, 'account_writes': 0,
    'package_writes': 0, 'provider_writes': 2, 'other_provider_writes': 0,
}
ORIGINAL_GATES = ('settings.pages', 'settings.roundtrip', 'settings.permissions')
COMPLETABLE_GATES = ('settings.pages', 'settings.roundtrip')
COMMON_GATES = ('identity', 'lifecycle', 'stability', 'data_permissions', 'release_scope', 'ui_observation')
REMAINING_GATES = ('settings.permissions',) + COMMON_GATES
ALL_GATES = ORIGINAL_GATES + COMMON_GATES


def route_argv(task, page):
    if type(task) is not int or task <= 0 or page not in ALL_PAGES:
        raise RuntimeError('EXACT_OBSERVED_TASK_AND_FIXED_SETTINGS_PAGE_REQUIRED')
    # All components are exported by this exact selected APK. A component
    # route avoids speculative action resolution (the System page has no
    # android.settings.SYSTEM_SETTINGS intent filter in this APK).
    return ['/system/bin/am', 'start-activity', '-W', '--user', '0', '--display', '0',
            '--task', str(task), '--activity-clear-top', '-n', page['component']]


def setting_write_argv(value):
    if value is not None and (type(value) is not str or value not in ('12', '24')):
        raise RuntimeError('ONLY_SELECTED_TIME_FORMAT_VALUES')
    argv = ['/system/bin/settings', '--user', '0']
    return argv + (['delete', 'system', 'time_12_24'] if value is None else
                   ['put', 'system', 'time_12_24', value])
