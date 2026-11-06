import hashlib,json,os,re,secrets,sys
raw=sys.stdin.buffer.read(22718)
assert len(raw)==22717 and hashlib.sha256(raw).hexdigest()=="fe089e0fc4de4f18762aa541e9efadba79aa14615749ef7ef0f6cf0fbfe5fbe8"
excluded=json.loads(raw)
assert type(excluded) is list and len(excluded)==len(set(excluded))==649 and all(type(x) is str and re.fullmatch(r"[0-9a-f]{32}",x) for x in excluded)
assert os.getuid()==os.geteuid()==1000
labels=["bili_r10_install_flow","bili_r10_install_state","ihg_r4_install_flow","ihg_r4_install_state","amazon_r4_install_flow","amazon_r4_install_state","bestbuy_r4_install_flow","bestbuy_r4_install_state"]
values=[secrets.token_hex(16) for _ in labels]
assert len(set(values))==8 and not set(values).intersection(excluded)
print(json.dumps({"schema":1,"purpose":"fresh current-cell02 four helper installation","generator":"secrets.token_hex(16)","labels":labels,"values":values,"count":8,"excluded_count":649,"excluded_sha256":hashlib.sha256(raw).hexdigest(),"no_redraw":True,"Main_actions":0,"Android_actions":0,"children_started":0,"filesystem_mutations":0},sort_keys=True,separators=(",",":")),flush=True)
