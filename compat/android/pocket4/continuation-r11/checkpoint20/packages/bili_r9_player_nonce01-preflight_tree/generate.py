import hashlib,json,os,secrets,sys
raw=sys.stdin.buffer.read(65537)
assert len(raw)==50681 and hashlib.sha256(raw).hexdigest()=='a57f1eff5efa975249980d04d7de53194206a4d5382e2ae46776494665ef3da5'
p=json.loads(raw)
labels=p['labels'];excluded=set(p['exclude_values'])
assert os.getuid()==os.geteuid()==1000
assert p['count']==146 and len(labels)==len(set(labels))==146
assert all(type(x) is str and 0<len(x)<200 for x in labels)
assert len(excluded)==155 and all(type(x) is str and len(x)==32 and set(x)<=set('0123456789abcdef') for x in excluded)
values={};seen=set(excluded)
for label in labels:
    value=secrets.token_hex(16)
    assert value not in seen
    seen.add(value);values[label]=value
assert len(set(values.values()))==146
print(json.dumps({'schema':'pocket4-bili-r9-player-fresh-nonce-v1','generator':'secrets.token_hex(16)','uid':os.getuid(),'spec':{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()},'count':146,'labels':labels,'nonces':values,'exclude_count':len(excluded),'all_distinct_and_excluded_old_values':True,'source_only_nonce_generation':True,'Android_commands':0,'UI_actions':0,'App_launches':0},sort_keys=True,separators=(',',':')),flush=True)
