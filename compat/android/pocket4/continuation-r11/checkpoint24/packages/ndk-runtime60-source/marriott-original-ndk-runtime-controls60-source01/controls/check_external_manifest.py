"""Four pure controls for external manifest-pin construction.
The real FixedSources constructor/verify methods run against one explicit synthetic
read_exact_file seam. No Main, device, file, child, or runtime route is entered.
"""
import hashlib
import json
import types

def need(value,code):
    if not value:
        raise AssertionError(code)

def whole(body):
    return {'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()}

def run_controls(phases_source,phases_pin):
    body=phases_source.encode('utf-8')
    need(whole(body)==phases_pin,'phase source exact pin')
    module=types.ModuleType('manifest_constructor_only')
    module.__file__='<exact-phase-source>'
    exec(compile(body,module.__file__,'exec'),module.__dict__)
    original=(module.PENDING_SOURCE_ROOT,module.PENDING_SOURCE_MANIFEST,module.read_exact_file)
    need(original[0] is None and original[1] is None,'source remains unbound')
    root='/synthetic-owned-ndk-source'
    sources={name:(body if name=='fixture_phases.py' else
                   ('# explicit synthetic '+name+'\n').encode())
             for name in module.FIXED_SOURCE_NAMES}
    manifest={'schema':'pocket4-original-ndk-fixture-source-v1',
              'files':{name:whole(value) for name,value in sources.items()}}
    raw=(json.dumps(manifest,sort_keys=True,indent=2)+'\n').encode()
    pinned=whole(raw)
    reads=[]
    def read(path,limit,pin=None):
        path=str(path)
        need(path.startswith(root+'/') and '/' not in path[len(root)+1:],
             'synthetic read outside fixed directory')
        name=path[len(root)+1:]
        need(name=='SOURCE_PINS.json' or name in sources,'synthetic unknown file')
        data=raw if name=='SOURCE_PINS.json' else sources[name]
        need(len(data)<=limit,'synthetic input bound')
        if whole(data)!=pin:
            raise RuntimeError('FIXED_WHOLE_FILE_PIN_CHANGED')
        reads.append(name)
        return data
    cases=[]
    def case(name,callback):
        callback()
        cases.append({'name':name,'passed':True})
    def reject(callback,code):
        try:
            callback()
        except RuntimeError as error:
            need(str(error)==code,'wrong constructor rejection')
        else:
            raise AssertionError('constructor unexpectedly accepted')
    try:
        module.read_exact_file=read
        case('unbound_source_root_stops_before_read',lambda:reject(
             lambda:module.FixedSources(pinned),'SOURCE_ONLY_OWN_ROOT_AND_MANIFEST_UNBOUND'))
        need(reads==[],'unbound source performed read')
        need(module.PENDING_SOURCE_ROOT is None,'embedded root remains unbound')
        def positive():
            value=module.FixedSources(pinned,source_root=root)
            need(value.pin==pinned and value.pin is not pinned and
                 value.files==manifest['files'] and
                 value.files['fixture_phases.py']==phases_pin,
                 'real self-member verified without self-embedded digest')
            need(reads.count('SOURCE_PINS.json')==2 and
                 set(reads[2:])==module.FIXED_SOURCE_NAMES and len(reads)==9,
                 'real constructor plus verify exact nine synthetic reads')
            pinned['sha256']='0'*64
            need(value.pin['sha256']!=pinned['sha256'],'caller dictionary alias retained')
            pinned['sha256']=whole(raw)['sha256']
        case('external_pin_qualifies_own_phase_and_is_copied',positive)
        def embedded():
            module.PENDING_SOURCE_MANIFEST=pinned
            try:
                reject(lambda:module.FixedSources(pinned,source_root=root),
                       'EXTERNAL_EXACT_SOURCE_MANIFEST_PIN_REQUIRED')
            finally:
                module.PENDING_SOURCE_MANIFEST=None
        case('self_embedded_manifest_authority_is_rejected',embedded)
        case('wrong_external_manifest_hash_is_rejected',lambda:reject(
            lambda:module.FixedSources({**pinned,'sha256':'0'*64},source_root=root),
            'FIXED_WHOLE_FILE_PIN_CHANGED'))
    finally:
        module.PENDING_SOURCE_ROOT,module.PENDING_SOURCE_MANIFEST,module.read_exact_file=original
    need(module.PENDING_SOURCE_ROOT is None and module.PENDING_SOURCE_MANIFEST is None and
         module.read_exact_file is original[2],'source seams not restored')
    need(len(cases)==4,'four fixed constructor cases')
    return {'schema':1,'ok':True,'cases':cases,'count':4,
            'real_FixedSources_constructor_and_verify_called':True,
            'explicit_synthetic_reads':len(reads),'actual_files_read':0,
            'children':0,'Main_or_Android':0,'runtime_qualified':False,
            'source_barriers_restored':True}
