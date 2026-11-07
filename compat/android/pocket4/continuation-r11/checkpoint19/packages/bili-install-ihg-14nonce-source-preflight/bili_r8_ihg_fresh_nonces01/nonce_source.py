import json,os,secrets
assert os.getuid()==os.geteuid()==1000
values=[secrets.token_hex(16) for _ in range(14)]
assert len(set(values))==14 and all(len(v)==32 for v in values)
print(json.dumps({'schema':1,'purpose':'bili-r8-install-and-ihg-explicit-search-destination','bili_r8_install':values[:2],'ihg_search_destination':values[2:],'count':14,'Main_actions':0,'Android_actions':0,'automatic_retry':False},sort_keys=True),flush=True)
