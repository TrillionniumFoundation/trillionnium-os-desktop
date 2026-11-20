from pathlib import Path
import ast,copy,hashlib,json,types
ROOT=Path(__file__).resolve().parent.parent
rows=[]

def run(name,op,ok):
 try:
  op();observed=True;error=None
 except (RuntimeError,KeyError,ValueError,TypeError) as failure:
  observed=False;error=str(failure)
 assert observed is ok,(name,error)
 rows.append({'case':name,'expected_accept':ok,'matched':True,'error':error})

for name,selected in [('native_release_guard.py',9),('native_calendar_release.py',1),('native_settings_release.py',13)]:
 source=ROOT/'source'/name;mod=types.ModuleType(name[:-3]);raw=source.read_bytes();exec(compile(raw,str(source),'exec'),mod.__dict__)
 def pin(name):return {'path':str(mod.CANONICAL_SOURCE_ROOT/name),'bytes':100,'sha256':'a'*64}
 catalog=[{'index':i,'preparation':pin('preparations/'+str(i)+'.json'),'entry':pin('source/'+str(i)+'.py')} for i in range(14)]
 selection={'schema':'current-application-preparation-selection-v1','selection_only':True,'Android_actions':0,'Main_actions':0,'CURRENT_writes':0,'new_runtime_acceptance_count':0,'full_Main_execute_or_full_runtime_seed_executed':False,'historical_runtime_credit_transferred':False,'runtime_qualified':False,'production_ready':False,'selected_preparations':[r['preparation'] for r in catalog]}
 selected_pin=catalog[selected]['preparation']
 run(name+':exact-current-fourteen',lambda:mod.selected_preparation(catalog,selection,selected_pin),True)
 run(name+':old-thirteen',lambda:mod.selected_preparation(catalog[:13],selection,selected_pin),False)
 run(name+':cross-profile',lambda:mod.selected_preparation(catalog,selection,catalog[0]['preparation']),False)
 for field,new in [('Android_actions',False),('runtime_qualified',True),('production_ready',True),('historical_runtime_credit_transferred',True),('selected_preparations',selection['selected_preparations'][:-1])]:
  bad=copy.deepcopy(selection);bad[field]=new;run(name+':selection-'+field,lambda b=bad:mod.selected_preparation(catalog,b,selected_pin),False)
 for label,mutate in [('boolean-index',lambda b:b[1].update(index=True)),('extra-catalog-field',lambda b:b[1].update(permission=True)),('writable-home-source',lambda b:b[1]['entry'].update(path='/home/alex/work/old.py')),('duplicate-path-separator',lambda b:b[1]['entry'].update(path=str(mod.CANONICAL_SOURCE_ROOT)+'/source//x.py')),('boolean-byte-count',lambda b:b[1]['entry'].update(bytes=True))]:
  bad=copy.deepcopy(catalog);mutate(bad);run(name+':'+label,lambda b=bad:mod.selected_preparation(b,selection,selected_pin),False)
 expected='536870912' if 'calendar' in name else '2147483648';cpu='50000 100000' if 'calendar' in name else '200000 100000'
 limits={'cpu.max':cpu,'memory.max':expected,'memory.swap.max':'0','pids.max':'64'}
 run(name+':actual-original-bounds-parser',lambda:mod.OwnedLeafResources._limits(limits),True)
 for field,new in [('cpu.max','max 100000'),('cpu.max','0 100000'),('cpu.max','200001 100000'),('memory.max','max'),('memory.max','2147483649'),('memory.swap.max','1'),('pids.max','65')]:
  bad=dict(limits);bad[field]=new;run(name+':wrong-bound-'+field+'='+new,lambda b=bad:mod.OwnedLeafResources._limits(b),False)
 # The core held-FD/body/owner/lock and OFD close implementations stay unchanged.
 base=ROOT.parent/'current-native-leaf-successor-20261120/source'/('native_leaf_release.py' if 'guard' in name else 'native_calendar_release.py')
 expected_base='4422ff3d6a9e51675c7a26015ee023490d1dff4cf31ed85f475919aee43dfea4' if 'guard' in name else '77d8a3439f5d544c67de9aa4965e4007474d7a4737ac86df0329010319dd4114'
 assert hashlib.sha256(base.read_bytes()).hexdigest()==expected_base,'exact original held-authority implementation'
 def methods(text):
  module=ast.parse(text);return {node.name:{n.name:ast.dump(n,include_attributes=False) for n in node.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))} for node in module.body if isinstance(node,ast.ClassDef)}
 before=methods(base.read_text());after=methods(raw.decode())
 for method in ['_directory','_file','_body','guard','admit_owned_leaf_resources','close','__enter__','__exit__']:
  assert before['ReleaseLease'][method]==after['ReleaseLease'][method],(name,method)
 rows.append({'case':name+':held-authority-and-close-methods-unchanged','matched':True,'methods':8})
output={'schema':'pocket4-canonical-fourteen-native-source-guard-controls-v1','passed':True,'cases':rows,'case_count':len(rows),'live_lease_constructed':False,'host_or_runtime_input_reads':0,'Android_actions':0,'runtime_qualified':False,'production_ready':False}
print(json.dumps(output,sort_keys=True))
