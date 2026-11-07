#!/usr/bin/env python3
"""Local once-only source packaging; no device calls or dispatch."""
from pathlib import Path
import ast,difflib,hashlib,io,json,subprocess,tokenize,types
HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'android-bili-r6-player-content-ready-03'
NAMES=('owned_navigation.py','stage_execute.py','make_request.py','INPUTS.json','README.md','video_navigation.py','controls_reveal.py','playback_controls.py')

def pin(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def writejson(path,value):path.write_text(json.dumps(value,sort_keys=True,ensure_ascii=False,indent=2)+'\n')
def astdata(source):return ast.dump(ast.parse(source),include_attributes=False).encode()

def main():
    review=HERE/'review-source';review.mkdir(exist_ok=False)
    layout=[];binding=json.loads((HERE/'fresh-bindings.json').read_bytes());diff=[];changed=[]
    for name in NAMES:
        if not name.endswith('.py'):continue
        path=HERE/name;raw=path.read_bytes();source=raw.decode();(review/name).write_bytes(raw)
        protected=set()
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type==tokenize.STRING and token.start[0]!=token.end[0]:protected.update(range(token.start[0]+1,token.end[0]+1))
        compact=''.join(line if i in protected else ' '*((len(line)-len(line.lstrip(' ')))//4)+line[len(line)-len(line.lstrip(' ')):] for i,line in enumerate(source.splitlines(True),1))
        assert astdata(source)==astdata(compact),name
        tokens=list(tokenize.generate_tokens(io.StringIO(compact).readline));edits={}
        excluded={tokenize.INDENT,tokenize.DEDENT,tokenize.NEWLINE,tokenize.NL,tokenize.ENDMARKER,tokenize.COMMENT}
        for a,b in zip(tokens,tokens[1:]):
            if a.end[0]==b.start[0] and a.type not in excluded and b.type not in excluded and tokenize.OP in (a.type,b.type) and a.end[1]<b.start[1]:
                edits.setdefault(a.end[0],[]).append((a.end[1],b.start[1]))
        lines=compact.splitlines(True)
        for row,spans in edits.items():
            for start,end in sorted(spans,reverse=True):
                assert not lines[row-1][start:end].strip()
                lines[row-1]=lines[row-1][:start]+lines[row-1][end:]
        compact=''.join(lines)
        assert astdata(source)==astdata(compact),name
        path.write_text(compact)
        layout.append({'file':name,'review_source':str((review/name).relative_to(HERE)),'before':pin(raw),'after':pin(compact.encode()),'AST_sha256':hashlib.sha256(astdata(source)).hexdigest(),'AST_identical':True,'multiline_string_bytes_preserved':True})
        normalized=source
        for old,new in binding['map'].items():normalized=normalized.replace(new,old)
        normalized=normalized.replace('/home/alex/work/pocket4-bilibili-r6-pause-resume-04','/home/alex/work/pocket4-bilibili-r6-pause-resume-03').replace('pocket4-bilibili-r6-player-content-ready04-20261105','pocket4-bilibili-r6-player-content-ready03-20261105')
        original=(BASE/name).read_text()
        if astdata(original)!=astdata(normalized):changed.append(name)
        diff.extend(difflib.unified_diff((ast.unparse(ast.parse(original))+'\n').splitlines(True),(ast.unparse(ast.parse(normalized))+'\n').splitlines(True),fromfile='content-ready03/'+name,tofile='content-ready04-normalized/'+name))
    assert changed==['video_navigation.py'],changed
    writejson(HERE/'layout-equivalence.json',{'schema':1,'files':layout,'total_bytes_saved':sum(x['before']['bytes']-x['after']['bytes'] for x in layout),'AST_semantics_preserved':True})
    (HERE/'normalized-runtime.patch').write_text(''.join(diff))
    writejson(HERE/'normalized-changes.json',{'schema':1,'changed_runtime_AST_after_fresh_binding_normalization':changed,'unchanged_runtime_AST_after_fresh_binding_normalization':['owned_navigation.py','stage_execute.py','make_request.py','controls_reveal.py','playback_controls.py'],'original_R6_helper_java_contract_and_adapter_unchanged':True})
    manifest={'schema':1,'files':{name:pin((HERE/name).read_bytes()) for name in sorted(NAMES)}}
    assert all(0<x['bytes']<=65536 for x in manifest['files'].values())
    (HERE/'SOURCE_PINS.json').write_text(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n')
    source_sha=pin((HERE/'SOURCE_PINS.json').read_bytes())['sha256']
    result=subprocess.run(['/usr/bin/python3','-B',str(HERE/'make_request.py'),'--write-once','--source-manifest-sha256',source_sha,'--output',str(HERE/'exact-request.json')],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    (HERE/'generation.stdout.json').write_bytes(result.stdout);(HERE/'generation.stderr.log').write_bytes(result.stderr)
    assert result.returncode==0 and not result.stderr,result.stderr.decode()
    request=json.loads((HERE/'exact-request.json').read_bytes());payload=request['stdin'].encode()
    m=types.ModuleType('pure_stage_packet_validator');m.__file__=str(HERE/'stage_execute.py')
    exec(compile((HERE/'stage_execute.py').read_bytes(),m.__file__,'exec'),m.__dict__)
    packet,files=m.checked_packet(payload)
    assert packet['source_manifest_sha256']==source_sha and set(files)==set(NAMES)|{'SOURCE_PINS.json'}
    for name in ('owned_navigation.py','make_request.py'):
        result=subprocess.run(['/usr/bin/python3','-B',str(HERE/name)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        assert not result.stderr and json.loads(result.stdout)['state']=='PLAN_ONLY'
        (HERE/(name[:-3]+'-default-plan.json')).write_bytes(result.stdout)
    result=subprocess.run(['/usr/bin/python3','-B',str(HERE/'check_content_ready.py')],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    (HERE/'check_content_ready.stdout.json').write_bytes(result.stdout);(HERE/'check_content_ready.stderr.log').write_bytes(result.stderr)
    assert result.returncode==0 and not result.stderr,result.stderr.decode()
    pins={'schema':1,'request':pin((HERE/'exact-request.json').read_bytes()),'stdin':pin(payload),'source_manifest':pin((HERE/'SOURCE_PINS.json').read_bytes()),'stable_key':request['idempotency_key'],'request_not_submitted':True,'stage_checked_packet_only':True}
    writejson(HERE/'request-pins.json',pins)
    print(json.dumps(pins,sort_keys=True))
if __name__=='__main__':main()
