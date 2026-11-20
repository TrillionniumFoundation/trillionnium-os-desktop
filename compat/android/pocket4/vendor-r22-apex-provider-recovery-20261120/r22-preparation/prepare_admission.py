from pathlib import Path
import ast, hashlib, json

ROOT = Path(__file__).resolve().parent
original = (ROOT/'base-support/admission_core.py').read_text()
tree = ast.parse(original); lines=original.splitlines(keepends=True)
functions = {n.name:''.join(lines[n.lineno-1:n.end_lineno]) for n in tree.body if isinstance(n,ast.FunctionDef)}
baseline=json.loads((ROOT/'R21-BASELINE.json').read_bytes())
assembly=json.loads((ROOT.parent/'p4_native_leaf_successor/ASSEMBLY.json').read_bytes())
header='''#!/usr/bin/python3
"""R22 pure admission of the actual R21 failure/recovery and a new CI cohort.

No command, source writer, lock acquisition, launcher or retry is exposed.
The worker must independently recheck every full reference and live retirement.
"""
from pathlib import PurePosixPath
import hashlib
import re
import stat

'''
header+='CURRENT = '+repr(assembly['source'])+'\n'
header+="CI_SCHEMA = 'p4-native-leaf-complete-source-and-release-ci-v1'\n"
header+="CI_STATE = 'ALL_CURRENT_ORDINARY_AND19_NORMAL_RELEASE_BUILDS_PASSED'\n"
start=original.index('BINARIES = ');end=original.index('\nR19 = ',start)
header+=original[start:end]+'\n'
header+="R21 = '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/vendor-build-20261120-9907-r21'\n"
header+='MANIFEST = '+repr(baseline['current_manifest'])+'\n'
header+='LOCKS = '+repr(baseline['current_locks'])+'\n'
history={
 'worker':(277931,'71e439b91b5363ed9f295589ea7b29f6404de1556b9e61af0d85c6640e4768e9'),
 'contract':(83652,'f88235f91532045e2037a42ce2a44623dc549075e93e041fb955c945d4876d3d'),
 'bundle':(3519,'8cdff199f34b0922fd12b23457c17e6162f810d51f199b24b6abe5b9f47dbf47'),
 'outer':(35232,'2449e863d9d96435e982ddac4675e97f6a5afd4905076f85179b18fdf1d40247'),
 'terminal':(538436,'1272d9ba69e958d8e4bdd3c1b2efbf7663f42a51e29cc760fb146ee5ad06e5bd'),
 'build':(330997,'88bf7e778a3d08c830f3c3e51f0e6f64e3b50feaf6a519a60d11dcb426219c1c'),
 'recovery':(9720,'057c4958dafb3aaab4b5982ca71e19a701f19c8e675dc4c46c9dbd93eb61f7f1'),
}
header+='HISTORY = '+repr(history)+'\n\n\n'
names=['need','content_reference','reference','command_reaped','validate_host_abi_custody']
body=header+'\n\n\n'.join(functions[n] for n in names)+'\n\n\n'
current=functions['validate_current_release']
current=current.replace('def validate_current_release(value, binary_refs):','def validate_current_release(value, binary_refs, provenance):')
current=current.replace('1555','1588').replace('new 2359 release','new complete release')
current=current.replace("'p4-r20-actual-current-release-ci-consumed-v1'","'p4-r22-actual-current-release-ci-consumed-v1'")
current=current.replace("len(commands) == 243 and len({x['name'] for x in commands}) == 243",
                        "len(commands) == 244 and len({x['name'] for x in commands}) == 244")
head_check="""    head = commands[0]
    need(head['name'] == 'actual-github-source-head'
         and head['argv'] == ['git', 'rev-parse', 'HEAD']
         and content_reference(head['stdout'])['bytes'] == 41
         and content_reference(head['stdout'])['sha256']
             == hashlib.sha256((provenance['github_commit'] + '\\n').encode()).hexdigest(),
         'actual original first Git child observed this complete checkout head')
"""
current=current.replace("    for row in commands:\n",head_check+"    for row in commands:\n")
insertion="""    need(type(provenance) is dict and set(provenance) == {'github_commit', 'github_run_id', 'source_chain'}
         and re.fullmatch('[0-9a-f]{40}', provenance['github_commit']) is not None
         and type(provenance['github_run_id']) is int and provenance['github_run_id'] > 0
         and all(value[k] == provenance[k] for k in provenance),
         'actual checked-out GitHub head/run and complete source chain')
    need(type(value['fresh_example_binaries']) is dict
         and len(value['fresh_example_binaries']) == 3,
         'all three original example binaries built without executing their mains')
"""
current=current.replace("    need(value['errors'] == []",insertion+"    need(value['errors'] == []")
body+=current+'\n\n\n'+(ROOT/'admission_r21_predicates.py.fragment').read_text()
target=ROOT/'admission_r22.py';target.write_text(body)
compile(body,str(target),'exec')
proof={'schema':'p4-r22-admission-source-preservation-v1','unchanged_complete_functions':names,
       'old_admission_bytes':len(original.encode()),'old_admission_sha256':hashlib.sha256(original.encode()).hexdigest(),
       'new_admission_bytes':len(body.encode()),'new_admission_sha256':hashlib.sha256(body.encode()).hexdigest(),
       'expected_ci_source':assembly['source'],'expected_ordinary_tests':1588,
       'actual_new_ci_consumed':False,'source_operations':0,'runtime_qualified':False,'production_ready':False}
(ROOT/'ADMISSION-SOURCE-PROOF.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof))
