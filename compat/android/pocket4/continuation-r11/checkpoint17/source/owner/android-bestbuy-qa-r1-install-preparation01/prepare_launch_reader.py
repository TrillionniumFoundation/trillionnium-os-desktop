"""Freeze a fixed safe reader using the actual BestBuy launch terminal pins."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import subprocess
import sys

B=Path('/workspace/scratch/94990735b266')
OLD=B/'android-ihg-launch-inspect01-results-reader-01'
OUT=B/'android-bestbuy-launch-inspect01-results-reader-01'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def pretty(v):return (json.dumps(v,sort_keys=True,indent=2)+'\n').encode()
def pin(raw):return {'bytes':len(raw),'sha256':sha(raw)}
old=(OLD/'read_summary.py').read_bytes()
assert pin(old)=={'bytes':7536,'sha256':'99abe052f06846f2d81ceb3a3b1350df14140a0fcf42236ca2496e69c8f84393'}
changes=[('com.ihg.apps.android','com.bestbuy.android'),('ihg','bestbuy'),('IHG','BESTBUY'),
 ('399444a5b72d53139b880a4afefdb31a','e5c3f2c938e436b52539d52cdbfab8c5'),
 ('704bf0640c6a207ad8177dfc0240896cc785b6fa6db34521fbea5cd02e42a6fd','4ac1247dfd9bba4cfb69c33331d7d4d4cd29b8c22651db7e7994ce40d47f0925'),
 ('10196','10198'),('10137','10130'),("'coordinator.json':13631,'stage.json':1710", "'coordinator.json':13536,'stage.json':1713")]
body=old.decode()
for before,after in changes:
 assert before in body,before
 body=body.replace(before,after)
ast.parse(body)
maker=(OLD/'make_summary_request.py').read_text()
assert len(maker.encode())==2537 and sha(maker.encode())=='432cfae012d9f4762e8ea517ae44f35c796f824f780c9c200b55d797a8a7f761'
maker=maker.replace('pocket4-ihg-','pocket4-bestbuy-').replace('99abe052f06846f2d81ceb3a3b1350df14140a0fcf42236ca2496e69c8f84393',sha(body.encode())).replace('len(raw)==7536','len(raw)=='+str(len(body.encode())))
assert not OUT.exists();OUT.mkdir(mode=0o700)
def save(n,raw):
 if isinstance(raw,str):raw=raw.encode()
 with (OUT/n).open('xb') as stream:stream.write(raw)
save('read_summary.py',body);save('make_summary_request.py',maker)
args=[sys.executable,'-I',str(OUT/'make_summary_request.py'),'--write-once',
 '--coordinator-sha256','1b9632bc59f615cf364e148d4dd5d14a5c540e48764616d1cfded9a904159b07',
 '--stage-sha256','8a1f5f8b6b24b8e53c47d409a4e2e4a8005d4b4695703e916160ab4b3d5ca60f',
 '--output',str(OUT/'request.json')]
r=subprocess.run(args,capture_output=True,timeout=10,check=True);assert not r.stderr
save('request-generation.json',r.stdout)
diff=''.join(difflib.unified_diff(old.decode().splitlines(True),body.splitlines(True),fromfile='IHG/read_summary.py',tofile='BestBuy/read_summary.py'))
save('source.diff',diff)
q=json.loads((OUT/'request.json').read_bytes());oq=json.loads((OLD/'request.json').read_bytes())
assert q['stdin']==body and {k:v for k,v in q.items() if k not in ('args','stdin','idempotency_key')}=={k:v for k,v in oq.items() if k not in ('args','stdin','idempotency_key')}
assert q['args'][:-1]==oq['args'][:-1]
review={'schema':1,'baseline':str(OLD),'baseline_reader':pin(old),'new_reader':pin(body.encode()),
 'only_fixed_scope_identity_nonce_source_and_actual_parent_pin_literals_changed':True,
 'runtime_reader_operations_bounds_no_raw_UI_and_parent_chain_unchanged':True,
 'actual_job':'1a1ae32ee9b-fc05-5e1d','actual_stdout':{'bytes':559,'sha256':'fac25293e6d63eaec7aea7c0ed43eb545e86e122cc2bb3990e61b339fb8d8fc1'},
 'actual_coordinator':{'bytes':13536,'sha256':'1b9632bc59f615cf364e148d4dd5d14a5c540e48764616d1cfded9a904159b07'},
 'actual_stage':{'bytes':1713,'sha256':'8a1f5f8b6b24b8e53c47d409a4e2e4a8005d4b4695703e916160ab4b3d5ca60f'},
 'phase_files_require_both_exact_original_parent_links':True,'device_actions':0,'submitted':False}
save('source-review.json',pretty(review))
rows={p.name:pin(p.read_bytes()) for p in sorted(OUT.iterdir())}
save('FROZEN.json',pretty({'schema':1,'files':rows,'request_not_submitted':True}))
print(json.dumps({'root':str(OUT),'request':pin((OUT/'request.json').read_bytes()),'reader':pin(body.encode()),'manifest':pin((OUT/'FROZEN.json').read_bytes()),'diff':pin(diff.encode()),'key':q['idempotency_key'],'device_actions':0}))
