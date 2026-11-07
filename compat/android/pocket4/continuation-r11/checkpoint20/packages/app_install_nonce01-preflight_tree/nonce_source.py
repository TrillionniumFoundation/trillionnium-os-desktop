import json,secrets,re,os
labels=[app+"_"+kind for app in ("bili","ihg","amazon","bestbuy") for kind in ("flow","state")]
values=[secrets.token_hex(32) for _ in labels]
assert len(values)==8 and len(set(values))==8 and all(re.fullmatch("[0-9a-f]{64}",x) for x in values)
print(json.dumps({"schema":"pocket4-current-install-nonce-pool-v1","generator":"secrets.token_hex(32)","uid":os.getuid(),"labels":labels,"nonces":dict(zip(labels,values)),"Android_commands":0,"UI_actions":0,"source_only_nonce_generation":True},sort_keys=True,separators=(",",":")),flush=True)
