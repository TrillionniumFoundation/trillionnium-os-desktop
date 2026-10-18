import ast,copy,hashlib,importlib.util,json,os,pathlib,re,shutil,subprocess,sys,traceback
sys.dont_write_bytecode=True
source=pathlib.Path('/workspace/scratch/ae1a8cf05419/trillionnium-os-desktop/support/build/evidence/2026-10-17-main47288-abi/verify.py');expected='b6d2522489311f3fb4d2853bcc16a9c25f651fc1c55ee78660963c51b8197741';out=pathlib.Path(sys.argv[1]);out.mkdir()
if hashlib.sha256(source.read_bytes()).hexdigest()!=expected:raise SystemExit('source changed')
spec=importlib.util.spec_from_file_location('main47288_verifier_independent',source);v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v);report=json.loads((source.parent/'raw/acceptance-report.json').read_bytes());checks={x['name']:x for x in report['checks']};results=[]
def require(value,message):
 if not value:raise ValueError(message)
def rejected(operation):
 try:operation()
 except (ValueError,OSError,KeyError,TypeError) as error:return {'error':type(error).__name__,'reason':str(error)}
 raise ValueError('tamper accepted')
def check(name,operation):
 try:detail=operation();results.append({'name':name,'passed':True,'detail':detail})
 except Exception:results.append({'name':name,'passed':False,'traceback':traceback.format_exc()})
check('no_assert_nodes',lambda:require(not any(isinstance(n,ast.Assert) for n in ast.walk(ast.parse(source.read_bytes()))),'assert found'))
check('raw_rust_helper_positive75',lambda:v.rust_cases(checks['rust'],report['discovered_rust_tests']))
check('raw_python_helper_positive52',lambda:v.python_cases(checks['python'],report['discovered_python_tests']))
c=copy.deepcopy(checks['rust']);c['stdout']=re.sub(r'^test .+ \.\.\. ok\n','',c['stdout'],count=1,flags=re.M)
check('rust_missing_named_test_rejected',lambda:rejected(lambda:v.rust_cases(c,report['discovered_rust_tests'])))
c=copy.deepcopy(checks['rust']);c['stdout']=c['stdout'].replace('0 filtered out','1 filtered out',1)
check('rust_filtered_summary_rejected',lambda:rejected(lambda:v.rust_cases(c,report['discovered_rust_tests'])))
c=copy.deepcopy(checks['rust']);c['stdout']=c['stdout'].replace(' ... ok\n',' ... ignored\n',1)
check('rust_ignored_named_case_rejected',lambda:rejected(lambda:v.rust_cases(c,report['discovered_rust_tests'])))
c=copy.deepcopy(checks['python']);c['stderr']=c['stderr'].replace(' ... ok\n'," ... skipped 'fixture'\n",1)
check('python_skipped_case_rejected',lambda:rejected(lambda:v.python_cases(c,report['discovered_python_tests'])))
c=copy.deepcopy(checks['python']);c['stderr']=re.sub(r'^test_\S+ \([^)]+\) \.\.\. ok\n','',c['stderr'],count=1,flags=re.M)
check('python_missing_named_case_rejected',lambda:rejected(lambda:v.python_cases(c,report['discovered_python_tests'])))
for label,line in [('parent_path','0'*64+'  ../outside\n'),('cache_input','0'*64+'  __pycache__/x.pyc\n')]:
 d=out/label;d.mkdir();(d/'SHA256SUMS').write_text(line);check('table_'+label+'_rejected',lambda d=d:rejected(lambda:v.table(d)))
d=out/'duplicate_table';d.mkdir();(d/'payload').write_bytes(b'fixture');line=hashlib.sha256(b'fixture').hexdigest()+'  payload\n';(d/'SHA256SUMS').write_text(line+line);check('table_duplicate_rejected',lambda:rejected(lambda:v.table(d)))
def clone(label):
 d=out/label;d.mkdir();names=[line.split('  ',1)[1] for line in (source.parent/'SHA256SUMS').read_text().splitlines()]+['SHA256SUMS']
 for name in names:
  dest=d/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((source.parent/name).read_bytes())
 return d
def resign(d):
 files=sorted(p for p in d.rglob('*') if p.is_file() and p!=d/'SHA256SUMS' and '__pycache__' not in p.relative_to(d).parts and p.suffix not in {'.pyc','.pyo'});(d/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(d))+'\n' for p in files))
def run(d,label,expected_exit):
 command=[sys.executable,'-I',*(['-O'] if sys.flags.optimize else []),str(d/'verify.py')];p=subprocess.run(command,cwd=out,capture_output=True,text=True);(out/(label+'.stdout.log')).write_text(p.stdout);(out/(label+'.stderr.log')).write_text(p.stderr);require(p.returncode==expected_exit,'unexpected verifier exit '+str(p.returncode));return {'command':command,'exit':p.returncode,'stderr':p.stderr}
d=clone('portable_copy');check('portable_full_bundle_positive',lambda:run(d,'portable-full',0))
d=clone('raw_tamper_outer_resigned');p=d/'raw/acceptance-report.json';data=json.loads(p.read_bytes());data['success']=False;p.write_text(json.dumps(data)+'\n');resign(d);check('raw_tamper_outer_resigned_rejected',lambda:run(d,'raw-tamper-outer',1))
d=clone('raw_tamper_both_resigned');p=d/'raw/acceptance-report.json';data=json.loads(p.read_bytes());data['success']=False;p.write_text(json.dumps(data)+'\n');resign(d/'raw');resign(d);check('raw_tamper_both_manifests_resigned_rejected',lambda:run(d,'raw-tamper-both',1))
result={'source_sha256':expected,'python_isolated':bool(sys.flags.isolated),'python_optimized':bool(sys.flags.optimize),'checks':len(results),'passed':all(x['passed'] for x in results),'tests':results,'acceptance_rerun':False,'new_kernel_QEMU_or_SDK':False};(out/'results.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps({'checks':result['checks'],'passed':result['passed'],'optimized':result['python_optimized']}));raise SystemExit(0 if result['passed'] else 1)
