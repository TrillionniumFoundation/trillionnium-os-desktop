"""Reproduce the nine frozen local input checks; no device or ART execution."""
from pathlib import Path
import ast,copy,hashlib,importlib.util,json,subprocess,sys
HERE=Path(__file__).parent
SOURCE=HERE/'verify_clock04.py'
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
source=SOURCE.read_bytes()
assert hashlib.sha256(source).hexdigest()=='2ac0b673f1b73b7e36542f961829b78c1b26d5549541a7b55cf4a8656f37797f'
m=load(SOURCE,'clock_art04_validation')
c=load(HERE.parent/'art-context05/read_context05.py','clock_context05_validation')
x=json.loads((HERE.parent/'art-context05/result05-original.json').read_bytes())
assert m.context_gate(x,c)==(x['declared_candidate_context'],list(reversed(c.LIBRARY_FILES)))
assert m.context_bytes((HERE.parent/'art-context05/current-oat.bin').read_bytes())['stored_clc_without_checksums']==x['declared_candidate_context']
checks=['actual context50/order and current OAT byte table accepted']
for name,mutate in [
    ('wrong-rc',lambda v:v['flatten_observation'].update(rc=0)),
    ('wrong-order',lambda v:v['flatten_observation'].update(stdout=':'.join(c.LIBRARY_FILES))),
    ('unjoined',lambda v:v['artifact_commands'][0].update(joined=False)),
    ('dependency-added',lambda v:v['declared_dependencies'].update({'androidx.window.extensions':'foreign'})),
    ('wrong-current-APK',lambda v:v['apk_before'].update(sha256='0'*64))]:
    value=copy.deepcopy(x);mutate(value)
    try:m.context_gate(value,c)
    except RuntimeError:checks.append(name+' rejected')
    else:raise AssertionError(name)
build=json.loads((HERE.parent/'build04-result-original.json').read_bytes())
main=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='main')
for node in ast.walk(main):
    if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='need' and len(node.args)>1 and isinstance(node.args[1],ast.Constant) and node.args[1].value=='ACTUAL_CLOCK_BUILD04_REQUIRED':
        assert eval(compile(ast.Expression(node.args[0]),'<actual-build04-check>','eval'),{},dict(build=build,APK_SHA=m.APK_SHA,DEX_SHA=m.DEX_SHA))
        checks.append('actual build04 required-condition true')
assert {'Lcom/android/deskclock/alarms/'+n[:-6]+';' for n in build['reviewed_targets']}==set(m.TARGETS)
checks.append('actual exact four changed descriptors equal')
r=subprocess.run([sys.executable,'-I',str(SOURCE)],capture_output=True,text=True,check=True)
assert json.loads(r.stdout)=={'state':'INERT','apk_sha256':m.APK_SHA,'installed':False,'UI_actions':0}
checks.append('default inert')
old=json.loads((HERE/'EXECUTION_REVIEW.json').read_bytes())
assert checks==old['checks'] and len(checks)==9
print(json.dumps({'checks':checks,'passed':9,'device_calls':0,'ART_execution':False,
    'scope':'Actual captured inputs and production gate functions only; does not simulate the compiler or App.'},sort_keys=True))
