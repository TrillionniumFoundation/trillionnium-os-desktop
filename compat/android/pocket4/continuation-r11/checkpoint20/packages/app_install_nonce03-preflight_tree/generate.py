import hashlib,json,os,secrets,sys
raw=sys.stdin.buffer.read(65537)
assert len(raw)==10721 and hashlib.sha256(raw).hexdigest()=='68d6177cbb57042cb2fc124d0800072a71eff88956918fdecb9bae2b1dc01198'
p=json.loads(raw);labels=p['labels'];seen=set(p['exclude_values'])
assert os.getuid()==os.geteuid()==1000
assert p['count']==6 and labels==['ihg_flow','ihg_state','amazon_flow','amazon_state','bestbuy_flow','bestbuy_state']
assert len(seen)==301 and all(type(x) is str and len(x)==32 and set(x)<=set('0123456789abcdef') for x in seen)
values={}
for label in labels:
    value=secrets.token_hex(16)
    assert value not in seen
    seen.add(value);values[label]=value
print(json.dumps({'schema':'pocket4-current-three-install-fresh-nonces-v1','generator':'secrets.token_hex(16)','uid':os.getuid(),'spec':{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()},'count':6,'labels':labels,'nonces':values,'excluded_count':301,'all_distinct_and_excluded_old_values':True,'source_only_nonce_generation':True,'Android_commands':0,'UI_actions':0,'App_launches':0},sort_keys=True,separators=(',',':')),flush=True)
