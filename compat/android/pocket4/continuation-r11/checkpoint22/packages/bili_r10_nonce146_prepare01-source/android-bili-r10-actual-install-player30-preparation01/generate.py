import hashlib,json,os,re,secrets,sys
raw=sys.stdin.buffer.read(131073)
assert 0<len(raw)<=131072 and hashlib.sha256(raw).hexdigest()=="c72f73bc4a413106297dd833f0de334f6502f336893df31c9831b3f1ebc6b6a2"
p=json.loads(raw)
assert p['schema']=='pocket4-bili-r10-current-owner-player-fresh146-spec-v1'
assert os.getuid()==os.geteuid()==1000
assert p['count']==146 and len(p['labels'])==len(set(p['labels']))==146
assert len(p['mapping'])==146 and [x['label'] for x in p['mapping']]==p['labels']
assert p['exclude_count']==len(p['exclude_values'])==len(set(p['exclude_values']))==741
assert all(type(v) is str and re.fullmatch('[0-9a-f]{32}',v) for v in p['exclude_values'])
assert p['actual_helper_UID']==10161 and p['source_only'] is True and p['UI_request_created'] is False
assert p['exact_one_draw_per_value'] is True and p['no_redraw'] is True
pool=[secrets.token_hex(16) for _ in range(146)]
assert len(pool)==len(set(pool))==146 and not set(pool)&set(p['exclude_values'])
print(json.dumps({'schema':'pocket4-bili-r10-current-owner-player-fresh146-v1',
 'spec':{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()},'count':146,
 'labels':p['labels'],'values':pool,'exclude_count':741,'all_distinct_and_old_values_excluded':True,
 'actual_helper_UID':p['actual_helper_UID'],'generator':'secrets.token_hex(16)','uid':os.getuid(),'no_redraw':True,
 'source_only_nonce_generation':True,'file_writes':0,'child_processes':0,'Android_commands':0,'App_launches':0,'UI_actions':0},sort_keys=True,separators=(',',':')),flush=True)
