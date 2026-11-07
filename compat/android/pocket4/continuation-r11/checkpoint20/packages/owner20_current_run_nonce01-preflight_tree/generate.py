import json,os,secrets
assert os.getuid()==os.geteuid()==1000
print(json.dumps({'schema':'pocket4-owner20-current-run-nonce-v1','generator':'secrets.token_hex(32)','profile':'p4-owner20-normal-20261106-01','attempt_nonce':secrets.token_hex(32),'uid':os.getuid(),'source_only_nonce_generation':True,'Android_commands':0,'UI_actions':0,'owned_runtime_started':False},sort_keys=True,separators=(',',':')),flush=True)
