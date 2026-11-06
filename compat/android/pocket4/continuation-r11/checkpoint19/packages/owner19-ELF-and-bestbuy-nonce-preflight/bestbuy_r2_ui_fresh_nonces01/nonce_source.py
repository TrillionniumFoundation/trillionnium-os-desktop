import json,os,secrets
assert os.getuid()==os.geteuid()==1000
values=[secrets.token_hex(16) for _ in range(4)]
assert len(set(values))==4 and all(len(v)==32 for v in values)
print(json.dumps({'schema':1,'purpose':'bestbuy-r2-fresh-launch-inspect','nonces':values,'count':4,'Main_actions':0,'Android_actions':0,'automatic_retry':False},sort_keys=True),flush=True)
