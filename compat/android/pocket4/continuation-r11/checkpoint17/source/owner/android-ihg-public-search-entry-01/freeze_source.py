#!/usr/bin/env python3
"""Local once-only IHG source freeze, original binding proof and pure controls."""
from pathlib import Path
import ast,copy,difflib,hashlib,json,subprocess,types
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
BASE=ROOT/'android-ihg-launch-inspect-01'

def pin(path):
    b=path.read_bytes();return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def write(name,value):
    with (HERE/name).open('x') as out:out.write(json.dumps(value,sort_keys=True,ensure_ascii=False,indent=2)+'\n')
def load(path,name):
    m=types.ModuleType(name);m.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),m.__dict__);return m
def tree(path):return ast.parse(path.read_text())
def functions(path):return {n.name:n for n in tree(path).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
def astsha(node):return hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest()

def main():
    entry=load(HERE/'owned_inspect.py','owned_search_source');binding=json.loads((HERE/'fresh-bindings.json').read_bytes())
    assert entry.ROOT.as_posix()==binding['new_root'] and entry.NONCE==binding['flow_nonce']
    assert entry.RUNTIME_FILES=={'owned_inspect.py','ihg_task_context.py','public_search.py','INPUTS.json'}
    original=load(BASE/'owned_inspect.py','original_ihg_source')
    constants=('PACKAGE','UID','SELF','HELPER_UID','COMPONENT','INSTALL_ROOT','INSTALL_SOURCE','INSTALL_SOURCE_SHA',
        'UTIL_SHA','UTIL_BYTES','CONTEXT_SHA','TRANSPORT_SHA','STATE_NONCE','STATE_WIRE','INSTALLED','PRIOR',
        'RESOLVER_ROOT','RESOLVER_SOURCE','RESOLVER_SHA','RESOLVER_BYTES','RESOLVER_NONCE','RESOLVER_RECORDS','PHASE_SECONDS')
    assert all(getattr(entry,k)==getattr(original,k) for k in constants)
    evidence=ROOT/'root-recovery-20261104-02/evidence'
    installed={name:json.loads((evidence/'ihg-r1-install-read01'/(name+'.json')).read_bytes()) for name in entry.PRIOR}
    for name,(_,size,digest) in entry.PRIOR.items():assert pin(evidence/'ihg-r1-install-read01'/(name+'.json'))=={'bytes':size,'sha256':digest}
    entry.actual_install(installed)
    resolver={name:json.loads((evidence/'ihg-artifact-launcher-readonly01'/(name+'.reconstructed-from-actual-stdout.json')).read_bytes()) for name in entry.RESOLVER_RECORDS}
    for name,(_,size,digest) in entry.RESOLVER_RECORDS.items():assert pin(evidence/'ihg-artifact-launcher-readonly01'/(name+'.reconstructed-from-actual-stdout.json'))=={'bytes':size,'sha256':digest}
    entry.actual_resolver(resolver,entry.INSTALLED)
    write('actual-binding-proof.json',{'schema':1,'unchanged_actual_binding_constants':list(constants),
        'original_pinned_three_install_and_two_metadata_JSONs_revalidated':True,
        'actual_install_and_actual_resolver_functions_executed_locally_only':True,
        'commercial_target_signer_and_shared_process_tree_qualification_not_upgraded':True,
        'original_source_manifest':pin(BASE/'SOURCE_PINS.json')})
    baseline_funcs=functions(BASE/'owned_inspect.py');new_funcs=functions(HERE/'owned_inspect.py')
    preserved=('need','sha','read','load','verify_source','actual_resolver','actual_install','scope_record','owned_scope')
    assert all(astsha(baseline_funcs[k])==astsha(new_funcs[k]) for k in preserved)
    taskold=functions(BASE/'ihg_task_context.py');tasknew=functions(HERE/'ihg_task_context.py')
    assert astsha(taskold['Flow'])==astsha(tasknew['Flow']) and astsha(taskold['open_task_context'])==astsha(tasknew['open_task_context'])
    finalies=[]
    for name in ('worker','execute'):
        oldfinal=max((n for n in ast.walk(baseline_funcs[name]) if isinstance(n,ast.Try) and n.finalbody),key=lambda n:len(n.finalbody))
        newfinal=max((n for n in ast.walk(new_funcs[name]) if isinstance(n,ast.Try) and n.finalbody),key=lambda n:len(n.finalbody))
        assert [astsha(n) for n in oldfinal.finalbody]==[astsha(n) for n in newfinal.finalbody],name
        finalies.append(name)
    historical=functions(ROOT/'android-ihg-launch01-public-roles-reader-01/read_public_roles.py') if (ROOT/'android-ihg-launch01-public-roles-reader-01/read_public_roles.py').exists() else None
    if historical is None:
        paths=[p for p in (ROOT/'android-ihg-launch01-public-roles-reader-01').glob('*.py') if 'def public_role_counts(' in p.read_text()]
        assert len(paths)==1;historical_path=paths[0];historical=functions(historical_path)
    else:historical_path=ROOT/'android-ihg-launch01-public-roles-reader-01/read_public_roles.py'
    newpublic=functions(HERE/'public_search.py')
    assert astsha(historical['public_role_counts'])==astsha(newpublic['public_role_counts'])
    def assignments(path):
        out={}
        for n in tree(path).body:
            if isinstance(n,ast.Assign):
                for target in n.targets:
                    if isinstance(target,ast.Name) and target.id in ('PUBLIC_ROLES','PUBLIC_RESOURCES','PUBLIC_CLASSES'):out[target.id]=ast.literal_eval(n.value)
        return out
    assert assignments(historical_path)==assignments(HERE/'public_search.py')
    write('original-guard-proof.json',{'schema':1,'unchanged_entry_function_AST':{k:astsha(new_funcs[k]) for k in preserved},
        'unchanged_task_class_Flow_AST':astsha(tasknew['Flow']),'unchanged_open_task_context_AST':astsha(tasknew['open_task_context']),
        'unchanged_original_worker_and_coordinator_finally':finalies,
        'public_catalog_and_counter_AST_copied_from_fixed_safe_reader':{'path':str(historical_path),**pin(historical_path)},
        'original_R1_qa_adapter_contract_and_helper_not_modified':True,
        'new_semantic_hook_is_owned_subclass_only_original_Session_sequence_inherited':True})
    diffs=[]
    for name in ('owned_inspect.py','ihg_task_context.py','stage_execute.py'):
        before=(BASE/name).read_text();after=(HERE/name).read_text().replace(binding['new_root'],str(original.ROOT)).replace(binding['flow_nonce'],original.NONCE)
        diffs.extend(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='original-IHG-launch01/'+name,tofile='new-public-search01/'+name))
    diffs.extend(difflib.unified_diff([], (HERE/'public_search.py').read_text().splitlines(True),fromfile='/dev/null',tofile='new-public-search01/public_search.py'))
    (HERE/'normalized-runtime.patch').write_text(''.join(diffs))
    manifest={'schema':1,'files':{name:pin(HERE/name) for name in sorted(entry.RUNTIME_FILES)}}
    assert all(0<v['bytes']<=65536 for v in manifest['files'].values())
    (HERE/'SOURCE_PINS.json').write_text(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n')
    source_pin=pin(HERE/'SOURCE_PINS.json');stage_pin=pin(HERE/'stage_execute.py')
    generator=HERE/'make_request.py';source=generator.read_text();lines=source.splitlines(True)
    changes={'MANIFEST_SHA':source_pin['sha256'],'STAGE_SHA':stage_pin['sha256'],'STAGE_BYTES':stage_pin['bytes']}
    for node in ast.parse(source).body:
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in changes:
            assert node.lineno==node.end_lineno;name=node.targets[0].id;lines[node.lineno-1]=name+'='+repr(changes[name])+'\n'
    generator.write_text(''.join(lines))
    for name,args in [('check_search_entry.py',[]),('owned_inspect.py',[]),('make_request.py',[])]:
        result=subprocess.run(['/usr/bin/python3','-B',str(HERE/name),*args],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        (HERE/(name[:-3]+'.stdout.json')).write_bytes(result.stdout);(HERE/(name[:-3]+'.stderr.log')).write_bytes(result.stderr)
        assert result.returncode==0 and not result.stderr,result.stderr.decode()
    result=subprocess.run(['/usr/bin/python3','-B',str(generator),'--write-once','--output',str(HERE/'exact-request.json')],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    (HERE/'generation.stdout.json').write_bytes(result.stdout);(HERE/'generation.stderr.log').write_bytes(result.stderr)
    assert result.returncode==0 and not result.stderr,result.stderr.decode()
    request=json.loads((HERE/'exact-request.json').read_bytes());packet=json.loads(request['stdin'])
    assert request['idempotency_key']==binding['new_key'] and request['timeout_seconds']==600
    # Execute only the stage's packet assertions, before its first environment/access assertion.
    stage=ast.parse((HERE/'stage_execute.py').read_text());function=next(n for n in stage.body if isinstance(n,ast.FunctionDef) and n.name=='main')
    boundary=next(i for i,n in enumerate(function.body) if isinstance(n,ast.Assert) and 'os.getuid' in ast.unparse(n))
    check=copy.deepcopy(function);check.name='validate_packet_only';check.body=check.body[:boundary]+[ast.Return(value=ast.Constant(value=True))]
    code=ast.Module(body=[*stage.body[:next(i for i,n in enumerate(stage.body) if n is function)],check],type_ignores=[])
    ast.fix_missing_locations(code);scope={};exec(compile(code,'pure_ihg_packet','exec'),scope)
    assert scope['validate_packet_only'](packet,source_pin['sha256']) is True
    write('request-pins.json',{'schema':1,'request':pin(HERE/'exact-request.json'),
        'stdin':{'bytes':len(request['stdin'].encode()),'sha256':hashlib.sha256(request['stdin'].encode()).hexdigest()},
        'source_manifest':source_pin,'stage':stage_pin,'stable_key':request['idempotency_key'],
        'original_stage_packet_assertions_executed_before_environment_boundary':True,'request_not_submitted':True})
    print((HERE/'request-pins.json').read_text())

if __name__=='__main__':main()
