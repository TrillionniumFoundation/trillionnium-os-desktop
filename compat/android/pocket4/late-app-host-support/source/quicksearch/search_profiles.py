"""Original signed QuickSearchBox and URL receiver; source facts are not UI credit."""
SEARCH = {'package': 'com.android.quicksearchbox', 'uid': 10069, 'version_code': 37,
    'component': 'com.android.quicksearchbox/.SearchActivity',
    'apks': [{'bytes': 758435, 'sha256': 'e30ebea932dabb06f6ba7ad50b093101e697e7896742f1fedcad223fca23fbc5'}],
    'certificate_sha256': '28bbfe4a7b97e74681dc55c2fbb6ccb8d6c74963733f6af6ae74d8c3a6e879fd', 'require_v3': False}
BROWSER = {'package': 'org.chromium.webview_shell', 'uid': 10060, 'version_code': 1,
    'component': 'org.chromium.webview_shell/.WebViewBrowserActivity',
    'apks': [{'bytes': 75170, 'sha256': '45e7be6309d8675cce6e2281f00d887c2e297b770fa19378b34350971dc8a06b'}],
    'certificate_sha256': 'a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc', 'require_v3': True}
NATIVE_HELPER = {'package': 'local.pocket4.actions.v2', 'uid': 10125, 'version_code': 2,
    'component': None, 'apks': [{'bytes': 20847, 'sha256': 'a5368465d5f6faef3299bf1ba6d6bde268cc8b37c72401c6e668872b24725058'}],
    'certificate_sha256': None, 'require_v3': False}
KINDS = ('search_online', 'search_offline', 'search_error')
QUERIES = ('中文', 'café')
GATES = {
    'search.failure': 'Verify empty/offline/error paths and lifecycle without a blank or unusable UI.',
    'search.open': 'Open a known result, return and verify query state.',
    'search.query': 'Enter Unicode queries with exact readback and verify matching local/web results.',
}
LIMITS = {'business_seconds': 420, 'cleanup_seconds': 60, 'maximum_UI_actions': 24,
    'maximum_native_launches': 2, 'native_launch_timeout': 45, 'maximum_handoffs': 1,
    'maximum_back_inputs': 1, 'maximum_read_observations_per_wait': 12,
    'permission_writes': 0, 'account_operations': 0, 'package_mutations': 0,
    'network_configuration_writes': 0}

def profiles(kind):
    if kind not in KINDS:
        raise RuntimeError('ONLY_ORIGINAL_QUICKSEARCH_BRANCHES')
    return SEARCH, NATIVE_HELPER, BROWSER, LIMITS
