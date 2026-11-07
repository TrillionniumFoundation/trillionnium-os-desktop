import hashlib,json,os,re,secrets,sys
raw=sys.stdin.buffer.read(65537)
assert len(raw)==59859 and hashlib.sha256(raw).hexdigest()=='694466b761ff46a01bc1f3bf5851c4faac4c8a8600531718ad49e31cc0d3d1f9'
p=json.loads(raw)
assert os.getuid()==os.geteuid()==1000
assert p['schema']=='pocket4-bili-r9-player02-fresh-nonce-spec-v1'
labels=p['labels'];excluded=p['exclude_values']
assert p['count']==146 and len(labels)==len(set(labels))==146
assert p['exclude_count']==337 and len(excluded)==len(set(excluded))==337
assert all(isinstance(s,str) and re.fullmatch('[0-9a-f]{32}',s) for s in excluded)
assert len(p['label_mapping'])==146 and [r['label'] for r in p['label_mapping']]==labels
assert all(r['old'] in excluded and len(r['slot'])==32 for r in p['label_mapping'])
values=[]
for _ in range(2048):
    value=secrets.token_hex(16)
    if value not in excluded and value not in values:values.append(value)
    if len(values)==146:break
assert len(values)==len(set(values))==146 and not set(values)&set(excluded)
out={'schema':'pocket4-bili-r9-player02-fresh-nonce-v1','generator':'secrets.token_hex(16)',
 'count':146,'exclude_count':337,'labels':labels,'nonces':dict(zip(labels,values)),
 'spec':{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()},
 'all_distinct_and_excluded_old_values':True,'prior_failed_146_not_reused':True,
 'source_only_nonce_generation':True,'uid':os.getuid(),'Android_commands':0,'UI_actions':0,'App_launches':0}
encoded=json.dumps(out,sort_keys=True,separators=(',',':'))
assert len(encoded.encode())<=32768
print(encoded,flush=True)
