from pathlib import Path
import ast,hashlib,json,subprocess
p=Path('/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/vendor-build-20261120-9907-r21/source.py')
b=p.read_bytes();assert hashlib.sha256(b).hexdigest()=='71e439b91b5363ed9f295589ea7b29f6404de1556b9e61af0d85c6640e4768e9'
t=ast.parse(b);nodes=[n for n in t.body if isinstance(n,ast.FunctionDef) and n.name in ('need','r21_retired_fields')];assert len(nodes)==2
ns={};exec(compile(ast.Module(body=nodes,type_ignores=[]),str(p),'exec'),ns);f=ns['r21_retired_fields']
service=b'LoadState=not-found\nActiveState=inactive\nSubState=dead\nMainPID=0\nControlGroup=\n';scope=b'LoadState=not-found\nActiveState=inactive\nSubState=dead\nControlGroup=\n'
rows=[]
def check(name,u,o,e,rc,accepted):
 try:f(u,o,e,rc);actual=True
 except (RuntimeError,ValueError,UnicodeDecodeError):actual=False
 assert actual==accepted,name
 rows.append({'case':name,'passed':True,'accepted':actual})
check('retired_service','fixture.service',service,b'',0,True)
check('retired_scope','fixture.scope',scope,b'',0,True)
for label,u,o,e,rc in [('service_missing_pid','fixture.service',scope,b'',0),('scope_extra_pid','fixture.scope',service,b'',0),('active_scope','fixture.scope',scope.replace(b'inactive',b'active'),b'',0),('loaded_scope','fixture.scope',scope.replace(b'not-found',b'loaded'),b'',0),('scope_cgroup','fixture.scope',scope.replace(b'ControlGroup=\n',b'ControlGroup=/live\n'),b'',0),('service_live_pid','fixture.service',service.replace(b'MainPID=0',b'MainPID=42'),b'',0),('duplicate_field','fixture.scope',scope+b'LoadState=not-found\n',b'',0),('stderr','fixture.scope',scope,b'error',0),('nonzero_exit','fixture.scope',scope,b'',1),('boolean_exit','fixture.scope',scope,b'',False),('invalid_utf8','fixture.scope',scope+b'\xff',b'',0),('unsupported_unit','fixture.timer',scope,b'',0),('malformed_line','fixture.scope',scope+b'bad\n',b'',0)]:check(label,u,o,e,rc,False)
units=['p4-cmake652-validation-20261118-appagent-r1.scope','p4-cp3a-vendor-supervisor-20261120-9907-r20.service'];actual=[]
for u in units:
 r=subprocess.run(['/usr/bin/systemctl','--user','show',u,'--property=LoadState,ActiveState,SubState,MainPID,ControlGroup'],capture_output=True,timeout=15,check=False)
 fields=f(u,r.stdout,r.stderr,r.returncode);actual.append({'unit':u,'returncode':r.returncode,'stdout':r.stdout.decode(),'stderr':r.stderr.decode(),'fields':fields})
assert p.read_bytes()==b
print(json.dumps({'schema':'p4-r21-retired-wire-direct-regression-v1','source_sha256':hashlib.sha256(b).hexdigest(),'cases':rows,'case_count':len(rows),'actual_units':actual,'only_ast_extracted_pure_parser_executed':True,'source_unchanged':True,'builds_started':0,'Android_starts':0,'production_ready':False},sort_keys=True))

