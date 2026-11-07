import ast,json,hashlib,importlib.util,contextlib,io
from pathlib import Path
r=Path('/workspace/scratch/94990735b266/android-qa-install-state-01')
p=r/'install_state.py'; spec=importlib.util.spec_from_file_location('owned_new_install',p); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
rows=[]
for name,raw,accept in [('new_uid',b'package:org.droidloom.qa.bili.r1 uid:10170\n',True),('bili_uid',b'package:org.droidloom.qa.bili.r1 uid:10117\n',False),('v2_uid',b'package:org.droidloom.qa.bili.r1 uid:10125\n',False),('multiple_user_uid',b'package:org.droidloom.qa.bili.r1 uid:10170,110170\n',False),('wrong_package',b'package:local.pocket4.actions.v2 uid:10170\n',False)]:
 try:m.uid_from(raw);ok=True
 except RuntimeError:ok=False
 assert ok==accept,name
 rows.append({'control':name,'pass':True})
x={'ok':True,'error':None,'secondary_errors':[]}
m.remember(x,'install',TimeoutError('owned timeout'))
m.remember(x,'release',OSError(9,'owned close'))
assert x['error']['type']=='TimeoutError' and x['secondary_errors'][0]['type']=='OSError' and x['ok'] is False
rows.append({'control':'first_error_preserved_with_release_secondary','pass':True})
assert '-R' in m.INSTALL and '-r' not in m.INSTALL and '-g' not in m.INSTALL and '-u' in m.PACKAGE_LIST and '-u' not in m.INSTALLED_ALL_USERS
assert len(m.NONCE)==len(m.STATE_NONCE)==32 and m.NONCE!=m.STATE_NONCE
for name in ['install_state.py','stage_execute.py','make_request.py','references/readonly_r3_coordinator.py']:ast.parse((r/name).read_bytes(),filename=name)
rows.append({'control':'actual_AST_and_fixed_package_flags_nonces','pass':True})
record={'schema':1,'scope':'actual new Python uid/first-error functions plus AST/constants only; no device, no namespace, no install, no UI, no Java rerun','pass':True,'controls':rows,'install_state_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
(r/'local-controls.json').write_text(json.dumps(record,indent=2)+'\n'); print(json.dumps(record))
