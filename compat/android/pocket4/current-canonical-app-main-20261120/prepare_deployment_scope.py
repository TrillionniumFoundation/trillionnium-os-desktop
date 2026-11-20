"""Freeze distinct app-qualification and original-data retention requirements.

Only the two original pinned JSON receipts were read. This generates source
for a future v2 transaction; it never rewrites an old transaction or data.
"""
import hashlib
import json
from pathlib import Path
import pprint

ROOT=Path(__file__).resolve().parent
raw=(ROOT/'evidence/APP-DATA-SCOPE.json').read_bytes()
assert len(raw)==31149 and hashlib.sha256(raw).hexdigest()=='b126b47947e93d300d4fe7eaa5b3f584ebae53db8300c622b21e8b30a8aef16f'
observed=json.loads(raw)
assert observed['image_opens']==observed['private_file_bodies_read']==observed['Android_actions']==observed['writes']==0
required=observed['required39'];preserved=observed['preserved45'];exemptions=observed['exemptions3']
assert len(required)==len(set(required))==39 and required==sorted(required)
assert [x['package'] for x in exemptions]==['com.enflick.android.TextNow','com.pinger.textfree','com.ubercab']
assert len(preserved)==45 and [x['package'] for x in preserved]==sorted({x['package'] for x in preserved})
assert sum(len(x['directories']) for x in preserved)==90
fields={
 'qualified_required39':{
  'schema':'pocket4-required-app-qualification-scope-v1',
  'meaning':'Required qualification set; this transaction field is not an app acceptance result.',
  'source_state':observed['sources'][0]['reference'],
  'required_packages':required,'required_count':39,'selected_count':42,
  'unavailable_APK_exemptions':exemptions,
  'individual_app_business_receipts_still_required':True},
 'preserved_original45':{
  'schema':'pocket4-original-app-data-retention-scope-v1',
  'meaning':'Original data protection set; app exemptions do not remove any protected directory.',
  'preimage':observed['sources'][1]['reference'],
  'package_count':45,'directory_count':90,'packages':preserved,
  'same_original_inode_and_mapped_owner_continuity_still_required':True},
 'preimages_retention':'retained until required39 current business acceptance and preserved_original45 data continuity are independently verified',
 'retention_release_requires':{
  'required39_current_runtime_business_receipts':True,
  'preserved_original45_current_data_continuity':True,
  'unresolved_supported_migrations':0,
  'app_exemption_is_not_data_deletion_permission':True}}
body='''"""Exact v2 transaction field producer and validator; no runtime authority.

The 39-app requirement set and 45-package original-data protection set are
independent. Nothing in this module accepts an app, releases a preimage,
migrates data, rewrites a historical receipt, or performs filesystem I/O.
Actual application receipts and same-original-data observations remain
separate requirements of the deployment and final cleanup consumers.
"""
import json

SCHEMA='pocket4-final-deployment-result-v2'
FIELDS='''+pprint.pformat(fields,width=110,sort_dicts=True)+'''

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)

def retention_fields():
    """Produce only requirement metadata for a fresh transaction writer."""
    return json.loads(canonical(FIELDS))

def validate_transaction(transaction):
    if type(transaction) is not dict or transaction.get('schema')!=SCHEMA:
        raise RuntimeError('EXPLICIT_NEW_TRANSACTION_SCOPE_VERSION_REQUIRED')
    if any(key not in transaction or canonical(transaction[key])!=canonical(value)
           for key,value in FIELDS.items()):
        raise RuntimeError('EXACT_REQUIRED39_AND_PRESERVED_ORIGINAL45_SCOPES_REQUIRED')
    # A version or field match cannot manufacture committed state or runtime
    # acceptance. The original transaction/data/qualified-Main gates follow.
    return True
'''
compile(body,'deployment_scope.py','exec')
(ROOT/'source/deployment_scope.py').write_text(body)
print('deployment_scope',len(body.encode()),hashlib.sha256(body.encode()).hexdigest())
