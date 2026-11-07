#!/usr/bin/env python3
"""Literal-only derivative of the reviewed IHG five-safe reader. No dispatch."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'android-ihg-launch-inspect01-results-reader-01'
COORD='8d950152a3eb3a4e0b62037717a79b6afd59f3a9a836af4a5c083f333ea83d4f'
STAGE='daf1f02e7f9ace7fd53e45bb07ee7bc1885a007144fa9eaa0d3b05451e4aa405'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def encoded(value):return (json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
def put(name,value):
    raw=value.encode() if isinstance(value,str) else value
    with (HERE/name).open('xb') as f:f.write(raw)
    return {'bytes':len(raw),'sha256':sha(raw)}

old=(BASE/'read_summary.py').read_bytes()
assert len(old)==7536 and sha(old)=='99abe052f06846f2d81ceb3a3b1350df14140a0fcf42236ca2496e69c8f84393'
mapping=[('pocket4-ihg-owned-launch-inspect-01','pocket4-ihg-public-search-entry-01'),
    ('399444a5b72d53139b880a4afefdb31a','c66c450fdd017a27e7c352a7b011cb21'),
    ('704bf0640c6a207ad8177dfc0240896cc785b6fa6db34521fbea5cd02e42a6fd','866d1e3ac277745e07fbcb75dcc103df27d611427392ac00577b3224a7b8f8ad'),
    ("'coordinator.json':13631,'stage.json':1710","'coordinator.json':39335,'stage.json':1717"),
    ('fixed-IHG-launch01-terminal-parents-and-three-parent-bound-phase-results','fixed-IHG-public-search01-terminal-parents-and-three-parent-bound-phase-results')]
source=old.decode()
for before,after in mapping:
    assert before in source;source=source.replace(before,after)
reader=put('read_summary.py',source)
maker=(BASE/'make_summary_request.py').read_text()
maker=maker.replace('99abe052f06846f2d81ceb3a3b1350df14140a0fcf42236ca2496e69c8f84393',reader['sha256'])
maker=maker.replace('len(raw)==7536','len(raw)=='+str(reader['bytes']))
maker=maker.replace('pocket4-ihg-launch-inspect01-five-safe-results-readonly-01-20261105','pocket4-ihg-public-search01-five-safe-results-readonly-01-20261106')
put('make_summary_request.py',maker)
put('literal-rebindings.json',encoded(mapping))
put('source.diff',''.join(difflib.unified_diff(old.decode().splitlines(True),source.splitlines(True),fromfile='IHG-launch01/read_summary.py',tofile='IHG-public-search01/read_summary.py')))
prior=old.decode()
for before,after in mapping:prior=prior.replace(before,after)
assert ast.dump(ast.parse(prior),include_attributes=False)==ast.dump(ast.parse(source),include_attributes=False)
for name in ('read_summary.py','make_summary_request.py'):compile((HERE/name).read_text(),name,'exec')
plan=subprocess.run([sys.executable,'-I','-B',str(HERE/'read_summary.py')],check=True,capture_output=True)
assert not plan.stderr;put('default-plan.json',plan.stdout)
done=subprocess.run([sys.executable,'-I','-B',str(HERE/'make_summary_request.py'),'--write-once',
    '--coordinator-sha256',COORD,'--stage-sha256',STAGE,'--output',str(HERE/'exact-request.json')],check=True,capture_output=True)
assert not done.stderr;put('request-pins.json',done.stdout)
request=json.loads((HERE/'exact-request.json').read_bytes())
assert request['stdin'].encode()==source.encode() and request['timeout_seconds']==30 and request['memory_max_bytes']==134217728
assert request['cpu_quota_percent']==100 and request['nice']==10
compile(request['args'][-1],'<verified-fixed-wrapper>','exec')
put('README.md','Literal-only binding of the reviewed five-safe IHG reader to the actual Search01 terminal parents. It reads fixed parent-bound launch/inspect/cleanup results only, preserving all bytes including the inspect outcome_unknown=true permitted by the separately reviewed action contract. It does not interpret outcome, grant UI release, export private assessments or raw trees, replay input, or claim hotel search/login/booking success.\n')
review={'schema':1,'state':'FROZEN_NOT_SUBMITTED','actual_terminal_job':'1a1ae4dec22-fc05-5edb',
    'base_reader':{'path':str(BASE/'read_summary.py'),'bytes':7536,'sha256':sha(old)},'reader':reader,
    'actual_external_parents':{'coordinator':{'bytes':39335,'sha256':COORD},'stage':{'bytes':1717,'sha256':STAGE}},
    'whole_AST_identical_after_explicit_literal_bindings':True,'runtime_logic_changes':[],
    'child_pins_from_exact_parent_only':True,'raw_tree_or_assessment_reads':0,'Hepta_or_UI_calls':0,
    'inspect_outcome_unknown_not_asserted_false':True,'actual_child_contents_not_yet_observed':True,
    'all_original_file_FD_privacy_deadline_and_size_bounds_unchanged':True}
put('source-review.json',encoded(review))
files={p.name:{'bytes':len(p.read_bytes()),'sha256':sha(p.read_bytes())} for p in sorted(HERE.iterdir()) if p.is_file()}
freeze=put('FROZEN_FILES.json',encoded({'schema':1,'files':files,'payload_count':len(files),'remote_actions':0}))
print(json.dumps({'request':files['exact-request.json'],'reader':reader,'source_review':files['source-review.json'],
    'frozen':freeze,'payload_count':len(files),'key':request['idempotency_key']},sort_keys=True))
