import hashlib,io,json,pathlib,re,tarfile
root=pathlib.Path('/workspace/scratch/ae1a8cf05419/main47288-abi-validation/publish-bundle');out=pathlib.Path(__file__).resolve().parent
checks=[]
def require(value,label):
 if not value:raise ValueError(label)
 checks.append(label)
def sha(data):return hashlib.sha256(data).hexdigest()
def read(name):return json.loads((root/name).read_bytes())
def blob(data):return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
manifest={}
for row in (root/'SHA256SUMS').read_text().splitlines():
 digest,name=row.split('  ',1);require(name not in manifest,'unique raw name '+name);require(sha((root/name).read_bytes())==digest,'raw SHA256 '+name);manifest[name]=digest
require(len(manifest)==36 and set(manifest)|{'SHA256SUMS'}=={p.name for p in root.iterdir()},'all original37 raw files accounted')
r=read('acceptance-report.json');m=read('acceptance-mutations.json');summary=read('summary.json');index=read('consumed-source.members.json');controller=read('controller-result.json');payloads={}
with tarfile.open(root/'consumed-source.tar.gz','r:gz') as archive:
 for member in archive:
  require(member.isfile() and member.name not in payloads and '..' not in pathlib.PurePosixPath(member.name).parts and not member.name.startswith('/'),'regular safe unique closure '+member.name)
  data=archive.extractfile(member).read();require(index[member.name]=={'bytes':len(data),'sha256':sha(data)},'indexed closure '+member.name);payloads[member.name]=data
require(len(payloads)==29 and set(payloads)==set(index),'all29 source closure members')
for name,digest in (r['input_sha256']|r['fixture_sha256']).items():require(sha(payloads[name])==digest,'acceptance input closure '+name)
require(r['input_sha256']==r['original_input_sha256_after'] and r['original_inputs_unchanged'] is True,'acceptance original inputs unchanged')
require(payloads['README.md']==b'' and r['readme_bytes']==0,'root README0')
require(blob(payloads['libs/os-abi/src/lib.rs'])=='356c76178a0b3a8a2a9babdf186b88977ec4d60c','newmethod source Git blob')
require(blob(payloads['libs/os-abi/tests/response_snapshot.rs'])=='105fd38a808561ff9628aa9b2eb3fdc8c2360bb7','newtest source Git blob')
records=controller['records'];require(len(records)==9 and controller['exit_code']==0,'controller9 commands all0')
for record in records:
 label=record['label'];require(record==read(label+'.command.json') and record['exit_code']==0,'exact actual command record '+label)
require((root/'source-head.stdout.log').read_text().strip()==summary['source_commit']==(root/'source-head-after.stdout.log').read_text().strip()=='47288c4465720d125658b392efc655b333c90868','beforeafter source commit47288')
require((root/'source-status-before.stdout.log').read_bytes()==(root/'source-status-after.stdout.log').read_bytes()==b'','actual beforeafter source clean')
require((root/'source-trees.stdout.log').read_text().splitlines()[0]==summary['source_tree']=='58c26d033df0b8b1476afa9aa0de185f46a03bd7','actual source tree')
accept=read('acceptance.command.json');require(accept['command'][1:3]==['-I','tests/abi/run_acceptance.py'] and '--mutation-timeout' in accept['command'] and accept['command'][-1]=='900','actual isolated acceptance/mutation budget900')
checks_by_name={v['name']:v for v in r['checks']};require(len(checks_by_name)==13 and r['success'] is True and r['errors']==[] and r['not_executed']==[],'all13 actual checks declared')
for name,c in checks_by_name.items():require(c['returncode']==0 and c['passed'] is True and c['timed_out'] is False,'check actually executed0 '+name)
for name in ('python','python_optimized'):
 c=checks_by_name[name];rows=re.findall(r'^test_\S+ \(([^)]+)\) \.\.\. (\S+)\s*$',c['stderr'],re.M);require(len(rows)==52 and all(v=='ok' for _,v in rows) and set(k for k,_ in rows)==set(r['discovered_python_tests']),'raw '+name+' exact52 discovered tests')
 require(re.findall(r'^Ran (\d+) tests? in ',c['stderr'],re.M)==['52'],'raw '+name+' denominator52')
rust=checks_by_name['rust'];totals=re.findall(r'^test result: (\w+)\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out;',rust['stdout'],re.M);names=re.findall(r'^test (.+) \.\.\. ok$',rust['stdout'],re.M)
require([sum(int(row[i]) for row in totals) for i in range(1,6)]==[75,0,0,0,0] and all(row[0]=='ok' for row in totals),'raw Rust75 zero failed ignored filtered')
require(len(names)==len(set(names))==75 and set(names)==set(r['discovered_rust_tests']),'raw Rust exact75 discovered tests')
require(sum(' - ' in name for name in names)==1 and 'src/lib.rs - Transport::decode_request_snapshot (line 226)' in names,'raw Rust74+1doctest')
ref=m['reference_toolchain_identity'];rustc_version=r['executables']['rustc']['version']['stdout'];require('commit-hash: 87e5904f5eb6398af6b22eac2802c78934260c48\n' in rustc_version and r['toolchain']=='nightly-2026-07-21','fixed actual Rust identity')
for name in ('baseline','baseline_semantic_edges','baseline_profile_boundaries'):
 b=m[name];require(b['source_sha256']==sha(payloads['libs/os-abi/src/lib.rs']) and b['compilation']['returncode']==b['test']['returncode']==0 and b['tests']['failed']==b['tests']['ignored']==b['tests']['filtered_out']==0,'actual original mutation baseline '+name)
require(m['expected_mutants']==m['mutants_killed']==len(m['mutants'])==12 and m['success'] is True and m['errors']==[],'all12 mutants reported killed')
for a in m['mutants']:
 require(a['compiled'] is True and a['compilation']['returncode']==0 and a['compilation']['timed_out'] is False and a['test']['returncode']==101 and a['test']['timed_out'] is False,'actual compiled kill '+a['name'])
 require(a['killed'] is True and a['expected_test_failed'] is True and a['tests']['ignored']==a['tests']['filtered_out']==0 and a['tests']['failed']>0,'designated failing assertion '+a['name'])
 for phase in ('toolchain_identity','test_toolchain_identity'):
  identity=a[phase];require(identity['valid'] is True and identity['cargo']['stdout']==ref['cargo']['stdout'] and identity['rustc']['stdout']==ref['rustc']['stdout'],'fixed identity '+phase+' '+a['name'])
require(sum(a['tests']['failed'] for a in m['mutants'])==17,'17 expected negative assertions')
result={'passed':True,'independent_conditions':len(checks),'checks':checks,'raw_files':37,'source_closure_files':29,'source_closure_archive_sha256':sha((root/'consumed-source.tar.gz').read_bytes()),'source_commit':summary['source_commit'],'source_tree':summary['source_tree'],'raw_sha256sums_sha256':sha((root/'SHA256SUMS').read_bytes()),'actual_check_count':13,'python_counts':[52,52],'rust_counts':{'unit_integration':74,'doctest':1},'mutants':12,'expected_negative_assertions':17,'acceptance_rerun':False,'payload_executed':False,'new_kernel_or_QEMU':False}
(out/'raw-audit-results.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='checks'},sort_keys=True))
