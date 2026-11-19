"""Original scoped inputs, never live authority or whole-app acceptance."""
DOCUMENTS={'package':'com.android.documentsui','uid':10022,'version_code':37,'component':None,
    'apks':[{'sha256':'757feffc32440dd371eaab4fb91f45273a621ee45b848e2dc734b386ac6e2086'}],
    'certificate_sha256':None,'require_v3':False}
PROVIDER={'package':'com.android.externalstorage','uid':10024,'version_code':37,'component':None,
    'apks':[{'sha256':'50d1e6f2be950e049cdc898dd812c8e609f421cc167013d4ee2c795dcdc0e5ea'}],
    'certificate_sha256':None,'require_v3':False}
NATIVE_HELPER={'package':'local.pocket4.actions.v2','uid':10125,'version_code':2,'component':None,
    'apks':[{'bytes':20847,'sha256':'a5368465d5f6faef3299bf1ba6d6bde268cc8b37c72401c6e668872b24725058'}],
    'certificate_sha256':None,'require_v3':False}
LIMITS={'business_seconds':600,'cleanup_seconds':120,'maximum_UI_actions':36,'reserved_cleanup_actions':4,
    'maximum_native_launches':2,'launch_timeout':45,'helper_install_maximum':1,'helper_uninstall_maximum':1,
    'helper_SystemCurrentTimeMillis_lease_ms':1200000,'account_mutations':0,'permission_writes':0,
    'user_file_content_reads':0,'host_fixture_content_writes':0,'unknown_action_replays':0}
REQUIRED_GATES={'NEW','CREATE_WRITE_READ_OK','PROVIDER_RENAME_OK','FILES_UI_RENAME','FILES_VIEW_OK',
    'OPEN_OK','REOPEN_OK','DELETE_PROVIDER_ACK','PROVIDER_DELETE_AND_ABSENCE'}
