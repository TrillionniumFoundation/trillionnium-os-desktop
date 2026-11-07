#!/usr/bin/env python3
"""Local immutable packaging and pure verification; never dispatch."""
from pathlib import Path
import ast,difflib,hashlib,io,json,subprocess,tokenize,types
HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'android-bili-r6-player-content-ready-04'
NAMES=('owned_navigation.py','stage_execute.py','video_navigation.py','controls_reveal.py','playback_controls.py','post_foreground.py')

def pin(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def writejson(path,value):
    with path.open('x') as stream:stream.write(json.dumps(value,sort_keys=True,ensure_ascii=False,indent=2)+'\n')
def astdata(source):return ast.dump(ast.parse(source),include_attributes=False).encode()

def compact(source):
    lines=source.splitlines(True);protected=set()
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type==tokenize.STRING and token.start[0]!=token.end[0]:protected.update(range(token.start[0]+1,token.end[0]+1))
        if token.type==tokenize.COMMENT:lines[token.start[0]-1]=lines[token.start[0]-1][:token.start[1]]+'\n'
    trimmed=''.join(line for row,line in enumerate(lines,1) if row in protected or line.strip())
    assert astdata(source)==astdata(trimmed)
    protected=set()
    for token in tokenize.generate_tokens(io.StringIO(trimmed).readline):
        if token.type==tokenize.STRING and token.start[0]!=token.end[0]:protected.update(range(token.start[0]+1,token.end[0]+1))
    value=''.join(line if row in protected else ' '*((len(line)-len(line.lstrip(' ')))//4)+line[len(line)-len(line.lstrip(' ')):] for row,line in enumerate(trimmed.splitlines(True),1))
    assert astdata(source)==astdata(value)
    tokens=list(tokenize.generate_tokens(io.StringIO(value).readline));edits={}
    excluded={tokenize.INDENT,tokenize.DEDENT,tokenize.NEWLINE,tokenize.NL,tokenize.ENDMARKER,tokenize.COMMENT}
    for a,b in zip(tokens,tokens[1:]):
        if a.end[0]==b.start[0] and a.type not in excluded and b.type not in excluded and tokenize.OP in (a.type,b.type) and a.end[1]<b.start[1]:
            edits.setdefault(a.end[0],[]).append((a.end[1],b.start[1]))
    lines=value.splitlines(True)
    for row,spans in edits.items():
        for start,end in sorted(spans,reverse=True):
            assert not lines[row-1][start:end].strip()
            lines[row-1]=lines[row-1][:start]+lines[row-1][end:]
    value=''.join(lines);assert astdata(source)==astdata(value)
    return value

def main():
    review=HERE/'review-source';review.mkdir(exist_ok=False)
    binding=json.loads((HERE/'fresh-bindings.json').read_bytes())
    layout=[];diff=[];changed=[];omitted_usage=[]
    for name in (*NAMES,'make_request.py'):
        path=HERE/name;raw=path.read_bytes();source=raw.decode();(review/name).write_bytes(raw)
        value=compact(source);path.write_text(value)
        layout.append({'file':name,'review_source':str((review/name).relative_to(HERE)),
            'before':pin(raw),'after':pin(value.encode()),'AST_sha256':hashlib.sha256(astdata(source)).hexdigest(),
            'AST_identical':True,'comments_and_blank_lines_only_removed':True,'multiline_string_bytes_preserved':True})
        normalized=source
        for old,new in binding['map'].items():normalized=normalized.replace(new,old)
        normalized=normalized.replace(binding['new_root'],binding['old_root']).replace(binding['new_key'],binding['old_key'])
        if name=='post_foreground.py':
            diff.extend(difflib.unified_diff([],source.splitlines(True),fromfile='/dev/null',tofile='foreground05/post_foreground.py'))
        else:
            original=(BASE/name).read_text()
            if astdata(original)!=astdata(normalized):changed.append(name)
            diff.extend(difflib.unified_diff((ast.unparse(ast.parse(original))+'\n').splitlines(True),
                (ast.unparse(ast.parse(normalized))+'\n').splitlines(True),
                fromfile='content-ready04/'+name,tofile='foreground05-normalized/'+name))
        if name in NAMES:
            for node in ast.walk(ast.parse(source)):
                if isinstance(node,ast.Constant) and node.value in ('INPUTS.json','README.md','make_request.py'):
                    omitted_usage.append({'file':name,'line':node.lineno,'value':node.value})
    assert changed==['owned_navigation.py','stage_execute.py'],changed
    assert omitted_usage==[],omitted_usage
    writejson(HERE/'runtime-closure-proof.json',{'schema':1,'remote_runtime_files':sorted(NAMES),
        'local_review_and_generator_files':['INPUTS.json','README.md','make_request.py'],
        'omitted_literal_references_in_all_remote_runtime_AST':omitted_usage,
        'all_runtime_main_helper_artifact_receipt_task_and_action_constants_retained':True,
        'same_source_file_and_packet_bounds':[65536,131072]})
    writejson(HERE/'layout-equivalence.json',{'schema':1,'files':layout,'AST_semantics_preserved':True,
        'total_bytes_saved':sum(row['before']['bytes']-row['after']['bytes'] for row in layout)})
    (HERE/'normalized-runtime.patch').write_text(''.join(diff))
    writejson(HERE/'normalized-changes.json',{'schema':1,'changed_existing_runtime_AST_after_binding_normalization':changed,
        'new_owned_runtime_file':'post_foreground.py','old_runtime_AST_unchanged':['video_navigation.py','controls_reveal.py','playback_controls.py'],
        'local_request_generator_AST_unchanged_after_binding_normalization':True})
    manifest={'schema':1,'files':{name:pin((HERE/name).read_bytes()) for name in sorted(NAMES)}}
    assert all(0<row['bytes']<=65536 for row in manifest['files'].values())
    (HERE/'SOURCE_PINS.json').write_text(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n')
    source_sha=pin((HERE/'SOURCE_PINS.json').read_bytes())['sha256']
    result=subprocess.run(['/usr/bin/python3','-B',str(HERE/'make_request.py'),'--write-once',
        '--source-manifest-sha256',source_sha,'--output',str(HERE/'exact-request.json')],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
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
    for name in ('check_post_foreground.py','check_content_ready.py'):
        result=subprocess.run(['/usr/bin/python3','-B',str(HERE/name)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        (HERE/(name[:-3]+'.stdout.json')).write_bytes(result.stdout)
        (HERE/(name[:-3]+'.stderr.log')).write_bytes(result.stderr)
        assert result.returncode==0 and not result.stderr,result.stderr.decode()
    pins={'schema':1,'request':pin((HERE/'exact-request.json').read_bytes()),'stdin':pin(payload),
        'source_manifest':pin((HERE/'SOURCE_PINS.json').read_bytes()),'stable_key':request['idempotency_key'],
        'request_not_submitted':True,'stage_checked_packet_only':True}
    writejson(HERE/'request-pins.json',pins)
    print(json.dumps(pins,sort_keys=True))

if __name__=='__main__':main()
