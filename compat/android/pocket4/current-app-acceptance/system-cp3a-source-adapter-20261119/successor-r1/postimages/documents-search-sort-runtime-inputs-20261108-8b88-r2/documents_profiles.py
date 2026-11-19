"""Original scoped inputs, never live authority or whole-app acceptance."""
DOCUMENTS={'package':'com.android.documentsui','uid':10022,'version_code':37,'component':None,
    'apks':[{'bytes': 8923434, 'sha256':'f7db1705178644333d5c9d291afd1170e71fcddfd1f73021381e1224be824899'}],
    'certificate_sha256':'c8a2e9bccf597c2fb6dc66bee293fc13f2fc47ec77bc6b2b0d52c11f51192ab8','require_v3':False}
PROVIDER={'package':'com.android.externalstorage','uid':10024,'version_code':37,'component':None,
    'apks':[{'sha256':'50d1e6f2be950e049cdc898dd812c8e609f421cc167013d4ee2c795dcdc0e5ea'}],
    'certificate_sha256':None,'require_v3':False}
NATIVE_HELPER={'package':'local.pocket4.actions.v2','uid':10125,'version_code':2,'component':None,
    'apks':[{'bytes':20847,'sha256':'a5368465d5f6faef3299bf1ba6d6bde268cc8b37c72401c6e668872b24725058'}],
    'certificate_sha256':None,'require_v3':False}
LIMITS={'business_seconds':750,'cleanup_seconds':150,'maximum_UI_actions':80,'reserved_cleanup_actions':4,
    'maximum_native_launches':3,'launch_timeout':45,'helper_install_maximum':1,'helper_uninstall_maximum':1,
    'helper_elapsedRealtime_lease_ms':1200000,'account_mutations':0,'permission_writes':0,'user_file_content_reads':0,
    'host_fixture_content_writes':0,'unknown_action_replays':0}
REQUIRED_GATES={'GET_CONTENT_CANCEL','TREE_CANCEL','EXACT_TREE_GRANT','FILES_NEW_FOLDER',
    'FILES_MULTIPLE_COPY','FILES_MULTIPLE_MOVE','FILES_MULTIPLE_DELETE_COPIES',
    'NORMAL_CLOSE_REOPEN_APP_READBACK','REVOKED_EXISTING_URI_SECURITY_DENIAL','GET_CONTENT_EXACT_FILE_READ',
    'FILES_UI_FINAL_DELETE','FINAL_GRANTS_EMPTY', 'FILES_VISIBLE_SORT', 'FILES_OWNED_SEARCH'}
