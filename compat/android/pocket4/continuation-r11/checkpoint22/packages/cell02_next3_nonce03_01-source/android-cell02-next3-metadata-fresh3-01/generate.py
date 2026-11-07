import hashlib,json,os,re,secrets,sys
raw=sys.stdin.buffer.read(65537)
assert 0<len(raw)<=65536 and hashlib.sha256(raw).hexdigest()=="cd6c5c935953ffac16a53f6bd45a28d444ec57d23b26b0d73bc566eb082101d7"
p=json.loads(raw)
assert p['schema']=='pocket4-fixed-next3-cell02-metadata-nonce-spec-v1'
assert os.getuid()==os.geteuid()==1000
assert p['labels']==["ticket12306.metadata","hilton.metadata","united.metadata"]
assert p['count']==3 and p['exclude_count']==len(p['exclude_values'])==len(set(p['exclude_values']))==887
assert all(type(x) is str and re.fullmatch('[0-9a-f]{32}',x) for x in p['exclude_values'])
values=[secrets.token_hex(16) for _ in range(3)]
assert len(values)==len(set(values))==3 and not set(values)&set(p['exclude_values'])
print(json.dumps({'schema':'pocket4-fixed-next3-cell02-metadata-nonces-v1','labels':p['labels'],'values':values,'count':3,'exclude_count':887,'controls_actual':p['controls_actual'],'source_pins':p['source_pins'],'spec':{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()},'generator':'secrets.token_hex(16)','uid':os.getuid(),'no_redraw':True,'distinct_and_all_excluded':True,'Android_commands':0,'App_launches':0,'UI_actions':0,'child_processes':0,'file_writes':0},sort_keys=True,separators=(',',':')),flush=True)
