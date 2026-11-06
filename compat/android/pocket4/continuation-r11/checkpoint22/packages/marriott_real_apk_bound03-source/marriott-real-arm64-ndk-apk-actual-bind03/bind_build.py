"""Bind the exact new configuration actual; preserve failed SDK22 and first-observe APK13."""
import argparse
import ast
import base64
import hashlib
import json
from pathlib import Path
import re
import stat

ROOT = Path(__file__).resolve().parent

def need(value, reason):
    if not value:
        raise RuntimeError(reason)

def read_pin(path, expected, maximum):
    need(type(expected) is str and re.fullmatch('[0-9a-f]{64}',expected),'expected complete SHA required')
    raw=path.read_bytes()
    need(0<len(raw)<=maximum and hashlib.sha256(raw).hexdigest()==expected,
         'complete binding input SHA/size differs: '+str(path))
    return raw

def terminal(raw, job, expected_stdout):
    value=json.loads(raw)
    need(value.get('job_id')==job and value.get('state')=='succeeded' and value.get('exit_code')==0 and
         value.get('output_complete') is True and value.get('output_durable') is True and
         value.get('terminal_publication_confirmed') is True and value.get('timed_out') is False and
         value.get('cancelled') is False and value.get('automatic_retry') is False,
         'exact reader terminal is not qualified')
    for k in ('stdout','stderr'):
        need(value['log_synced'][k] is True and value['log_truncated'][k] is False and
             value['log_errors'][k] is None,'reader output integrity differs')
    need(value['log_bytes']['stdout']=={'seen':expected_stdout,'stored':expected_stdout} and
         value['log_bytes']['stderr']=={'seen':0,'stored':0},'terminal byte counts differ')
    return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
            'base64':base64.b64encode(raw).decode('ascii'),'job_id':job}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for prefix in ('sdk_configuration',):
        p.add_argument('--'+prefix,required=True,type=Path)
        p.add_argument('--'+prefix+'-sha256',required=True)
        p.add_argument('--'+prefix+'-terminal',required=True,type=Path)
        p.add_argument('--'+prefix+'-terminal-sha256',required=True)
        p.add_argument('--'+prefix+'-job',required=True)
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args()
    pins=json.loads((ROOT/'SOURCE_PINS.json').read_bytes())
    need(pins.get('schema')==1 and set(pins['files']) ==
         {'build-template.py','config-pending.json','bind_build.py'},
         'fixed source pin set differs')
    for name,spec in pins['files'].items():
        raw=(ROOT/name).read_bytes()
        need(len(raw)==spec['bytes'] and hashlib.sha256(raw).hexdigest()==spec['sha256'],
             'frozen source differs: '+name)
    source=(ROOT/'build-template.py').read_text()
    cfg=json.loads((ROOT/'config-pending.json').read_bytes())
    need(cfg.get('script_only_pending_actuals') is True and
         cfg.get('actual_sdk_configuration') is None and
         type(cfg.get('actual_sdk22_failed_original')) is dict and 'actual_apk13' not in cfg,
         'source template was already bound')
    for prefix in ('sdk_configuration',):
        raw=read_pin(getattr(args,prefix),getattr(args,prefix+'_sha256'),1048576)
        status=read_pin(getattr(args,prefix+'_terminal'),
                        getattr(args,prefix+'_terminal_sha256'),32768)
        cfg['actual_'+prefix]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
             'base64':base64.b64encode(raw).decode('ascii'),
             'terminal':terminal(status,getattr(args,prefix+'_job'),len(raw))}
    # Extract only these original pure production validators: no module-level
    # imports, resource construction, child lifecycle, file reads, or main.
    module=ast.parse(source,'frozen-build-template.py')
    wanted={'require','digest','qualify_input_rows','exact_reader_binding',
            'original_sdk22_inputs','qualified_sdk_bindings'}
    functions=[n for n in module.body if isinstance(n,ast.FunctionDef) and n.name in wanted]
    need(len(functions)==6 and {n.name for n in functions}==wanted,'actual validator AST set differs')
    scope={'CFG':cfg,'base64':base64,'hashlib':hashlib,'json':json,'re':re,'stat':stat}
    extracted=ast.Module(body=functions,type_ignores=[])
    exec(compile(ast.fix_missing_locations(extracted),'<six-production-input-validators>','exec'),scope)
    old_failed,configuration,_,_=scope['qualified_sdk_bindings']()
    need(configuration.get('sdk_configuration_join',{}).get(
         'qualified_for_fixed_build_input_binding') is True and
         old_failed.get('collection_complete') is False,
         'new configuration source join or original failed status differs')
    cfg['script_only_pending_actuals']=False
    config_text=json.dumps(cfg,indent=2,sort_keys=True)+'\n'
    needle='CFG = None  # The immutable packet generator fills this exactly once.'
    need(source.count(needle)==1 and "'''" not in config_text,'immutable binding slot differs')
    bound=source.replace(needle,"CFG = json.loads(r'''"+config_text+"''')",1)
    ast.parse(bound,'actual-bound-build.py')
    sha=hashlib.sha256(bound.encode()).hexdigest()
    request={'host':'pocket4','executable':'/usr/bin/python3','args':['-I','-B','-'],
       'cwd':'/home/alex/work','stdin':bound,'timeout_seconds':660,
       'cpu_quota_percent':100,'memory_max_bytes':1073741824,'nice':15,
       'idempotency_key':'p4-marriott-real-arm64-ndk-apk-build03-'+sha[:16]}
    output=args.output
    need(not output.exists() and not output.is_symlink(),'binding output must be new')
    output.mkdir(mode=0o700)
    payloads={'build.py':bound,'config.json':config_text,
              'exact-request.json':json.dumps(request,indent=2,sort_keys=True)+'\n'}
    manifest={}
    for name,body in payloads.items():
        with (output/name).open('x',encoding='utf-8',newline='') as stream:
            stream.write(body)
        manifest[name]={'bytes':len(body.encode()),'sha256':hashlib.sha256(body.encode()).hexdigest()}
    summary={'schema':1,'files':manifest,'Android_actions':0,'children_started':0,
        'build_executed':False,'bound_input_jobs':['1a1b19b46a3-fc05-79d7',args.sdk_configuration_job],
        'original_sdk22_terminal_exit1_preserved':True,
        'APK13_observation_is_new_in_this_build':True,'old_reader02_qualification_borrowed':False,
        'normal_runtime_or_install_admitted':False}
    with (output/'BOUND_PINS.json').open('x',encoding='utf-8',newline='') as stream:
        stream.write(json.dumps(summary,indent=2,sort_keys=True)+'\n')
    print(json.dumps(summary,sort_keys=True))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
