import hashlib,json,os,re,secrets,sys
raw=sys.stdin.buffer.read(131073)
assert 0<len(raw)<=131072 and hashlib.sha256(raw).hexdigest()=='f8fcddaf16cf7223954a94c68ba7996557bf971782dd8a2a7379e05c079c0c58'
p=json.loads(raw)
assert p['schema']=='pocket4-current-amazon-bestbuy-fresh-flow-nonce-spec-v1'
assert os.getuid()==os.geteuid()==1000
assert p['count']==42 and len(p['labels'])==len(set(p['labels']))==42
assert len(p['mapping'])==42 and [x['label'] for x in p['mapping']]==p['labels']
assert [x['app'] for x in p['mapping']]==['amazon']*32+['bestbuy']*10
assert len(p['exclude_values'])==len(set(p['exclude_values']))==p['exclude_count']==699
assert all(type(x) is str and re.fullmatch('[0-9a-f]{32}',x) for x in p['exclude_values'])
assert p['source_only'] is True and p['Android_actions']==0 and p['UI_requests_created'] is False
assert p['exact_one_draw_per_value'] is True and p['no_redraw'] is True
pool=[secrets.token_hex(16) for _ in range(42)]
assert len(pool)==len(set(pool))==42 and not set(pool)&set(p['exclude_values'])
print(json.dumps({'schema':'pocket4-current-amazon-bestbuy-fresh-flow-nonce-v1',
    'spec':{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()},
    'count':42,'labels':p['labels'],'nonces':dict(zip(p['labels'],pool)),
    'exclude_count':p['exclude_count'],'all_distinct_and_old_values_excluded':True,
    'generator':'secrets.token_hex(16)','uid':os.getuid(),'no_redraw':True,
    'actual_helper_uids':p['actual_helper_uids'],
    'source_only_nonce_generation':True,'file_writes':0,'child_processes':0,
    'Android_commands':0,'App_launches':0,'UI_actions':0},sort_keys=True,separators=(',',':')),flush=True)
