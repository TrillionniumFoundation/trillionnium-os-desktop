"""Bounded nonce material only; no file, process, Android or Main operation."""
import hashlib,json,re,secrets,sys
raw=sys.stdin.buffer.read(16385)
assert 0<len(raw)<=16384 and hashlib.sha256(raw).hexdigest()=='858ec2a5aadbc3fca76f4a23a33a489ec185f7e169e4189d2118c4c529433082'
p=json.loads(raw)
assert set(p)=={'schema','purpose','count','nonce_exclusions'} and p['schema']==1
assert p['purpose']=='fresh-bili-r8-flow-nonce-pool-only' and p['count']==146
old=p['nonce_exclusions']
assert type(old) is list and len(old)==len(set(old))==296
assert all(type(v) is str and re.fullmatch('[0-9a-f]{32}',v) for v in old)
pool=[]
for _ in range(1024):
    value=secrets.token_hex(16)
    if value not in old and value not in pool:pool.append(value)
    if len(pool)==146:break
assert len(pool)==len(set(pool))==146,'BOUNDED_SECURE_NONCE_POOL_EXHAUSTED'
print(json.dumps({'schema':1,'ok':True,'purpose':p['purpose'],'count':146,
 'secrets_nonce_pool':pool,'nonce_exclusions_count':len(old),
 'source_input_sha256':hashlib.sha256(raw).hexdigest(),'disjoint_exclusions':True,
 'file_writes':0,'Android_actions':0,'Main_actions':0,'child_processes':0,
 'automatic_retry':False,'UI_flow_dispatched':False},sort_keys=True,separators=(',',':')),flush=True)
