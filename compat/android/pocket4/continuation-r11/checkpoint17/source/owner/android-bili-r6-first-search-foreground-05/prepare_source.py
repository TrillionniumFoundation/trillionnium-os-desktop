#!/usr/bin/env python3
"""Create new local candidate from exact frozen04; never dispatch or touch Android."""
from pathlib import Path
import ast,copy,hashlib,json,secrets,textwrap
HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'android-bili-r6-player-content-ready-04'

def pin(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def write(name,raw):
    path=HERE/name
    with path.open('xb') as stream:stream.write(raw)

def main():
    oldmanifest=(BASE/'SOURCE_PINS.json').read_bytes()
    assert pin(oldmanifest)=={'bytes':905,'sha256':'a49770d55b487e4e172aa38ebc1a454220ec7e668c499f8c8d5b838962e9da42'}
    for name,row in json.loads(oldmanifest)['files'].items():assert pin((BASE/name).read_bytes())==row,name
    oldmap=json.loads((BASE/'fresh-bindings.json').read_bytes())['map']
    mapping={value:secrets.token_hex(16) for value in oldmap.values()}
    assert len(mapping)==134 and len(set(mapping.values()))==134 and not set(mapping)&set(mapping.values())
    oldroot='/home/alex/work/pocket4-bilibili-r6-pause-resume-04'
    newroot='/home/alex/work/pocket4-bilibili-r6-pause-resume-05'
    oldkey='pocket4-bilibili-r6-player-content-ready04-20261105'
    newkey='pocket4-bilibili-r6-first-search-foreground05-20261106'
    write('fresh-bindings.json',(json.dumps({'schema':1,'map':mapping,'old_root':oldroot,'new_root':newroot,
        'old_key':oldkey,'new_key':newkey,'helper_nonce_count':133,'total_nonce_count':134},sort_keys=True,indent=2)+'\n').encode())
    for name in ('owned_navigation.py','stage_execute.py','make_request.py','video_navigation.py','controls_reveal.py','playback_controls.py'):
        source=(BASE/'review-source'/name).read_text()
        for old,new in mapping.items():source=source.replace(old,new)
        source=source.replace(oldroot,newroot).replace(oldkey,newkey)
        if name in ('owned_navigation.py','stage_execute.py'):
            source=source.replace("'owned_navigation.py','stage_execute.py','make_request.py','INPUTS.json','README.md','video_navigation.py','controls_reveal.py','playback_controls.py'}",
                "'owned_navigation.py','stage_execute.py','video_navigation.py','controls_reveal.py','playback_controls.py','post_foreground.py'}")
        if name=='owned_navigation.py':
            changes={
                "'EXACT_SEVEN_FILE_SOURCE_REQUIRED'":"'EXACT_SIX_RUNTIME_FILE_SOURCE_REQUIRED'",
                'def navigation_sequences(prior, qa, flow, session, installed, result):':'def navigation_sequences(prior, qa, flow, session, installed, result, first_click):',
                "result['click_sequence'] = session.sequence(fixed_plan())":"result['click_sequence'] = first_click.run(session,fixed_plan())",
                'def public_query_sequences(prior, qa, flow, session, installed, result):':'def public_query_sequences(prior, qa, flow, session, installed, result, first_click):',
                'navigation_sequences(prior,qa,flow,session,installed,result)':'navigation_sequences(prior,qa,flow,session,installed,result,first_click)',
                'public_query_sequences(prior,qa,flow,session,installed,result)':'public_query_sequences(prior,qa,flow,session,installed,result,video.first_click)',
            }
            for before,after in changes.items():
                assert source.count(before)==1,(name,before)
                source=source.replace(before,after)
            before="    return module\n\n\ndef worker"
            after="    path=HERE/'post_foreground.py';pin=manifest['files'][path.name]\n    module.first_click=types.ModuleType('owned_first_search_foreground');module.first_click.__file__=str(path)\n    exec(compile(read(path,65536,pin['sha256'],pin['bytes']),str(path),'exec'),module.first_click.__dict__)\n    module.first_click.validate(adapter,qa,PLAN)\n    return module\n\n\ndef worker"
            assert source.count(before)==1
            source=source.replace(before,after)
        write(name,source.encode())
    plan=next(ast.literal_eval(node.value) for node in ast.parse((HERE/'owned_navigation.py').read_text()).body
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PLAN' for t in node.targets))
    original=(HERE.parent/'owned-bili-qa-r6-reveal-01/source/qa_adapter.py').read_text()
    assert pin(original.encode())=={'bytes':25231,'sha256':'1e939fb27aa4eaa9bb2fd79d7022ff4f48011fdf8824b0e7645bbc6f3308e1c8'}
    cls=next(n for n in ast.parse(original).body if isinstance(n,ast.ClassDef) and n.name=='Session')
    node=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='sequence')
    copied=textwrap.dedent(''.join(original.splitlines(True)[node.lineno-1:node.end_lineno]))
    copied=copied.replace('def sequence(self, plan):','def owned_sequence(self, plan):')
    before="result['foreground_after'] = self.foreground()"
    assert copied.count(before)==1
    copied=copied.replace(before,"result['foreground_after'] = observe_post_ack(self,plan,result)")
    path=HERE/'post_foreground.py';source=path.read_text()
    assert 'def owned_sequence(' not in source
    source=source.replace('FIRST_PLAN = None  # The local generator binds the exact fresh first-click plan.',
        'FIRST_PLAN = '+repr(plan))
    path.write_text(source+'\n\n'+copied+'\n')
    write('check_content_ready.py',(BASE/'check_content_ready.py').read_bytes())
    write('original-structure-projection.json',(BASE/'original-structure-projection.json').read_bytes())
    oldinputs=json.loads((BASE/'INPUTS.json').read_bytes())
    encoded=json.dumps(oldinputs,sort_keys=True,ensure_ascii=False,separators=(',',':'))
    for old,new in mapping.items():encoded=encoded.replace(old,new)
    encoded=encoded.replace(oldroot,newroot).replace('SOURCE_CANDIDATE_CONTENT_READY04_ACTUAL_R6_INSTALL_BOUND_UI_NOT_RUN',
        'SOURCE_CANDIDATE_FIRST_SEARCH_FOREGROUND05_UI_NOT_RUN')
    full=json.loads(encoded)
    full['first_search_post_ack_foreground']={'only_first_actual_explicit_null_may_wait':True,'maximum_samples':3,
        'qualification_deadline_seconds':12,'original_command_timeout_seconds':15,'commands_are_readonly':True,
        'shared_recorder_backend_contract_and_adapter_unchanged':True,'failed_or_foreign_or_multiple_first_focus_stops':True,
        'no_input_replay_or_historical_error_reclassification':True,'original_after_state_restoration_required':True}
    fullraw=(json.dumps(full,sort_keys=True,ensure_ascii=False,indent=2)+'\n').encode()
    full['packaging']={'remote_runtime_closure_count':6,'review_only_files_not_executed_by_remote_entry':
        ['INPUTS.json','README.md','make_request.py'],'source_packet_limit_bytes':131072}
    write('INPUTS.json',(json.dumps(full,sort_keys=True,ensure_ascii=False,indent=2)+'\n').encode())
    write('README.md',('Bili R6 future first-search foreground candidate. Original first-click Session guard and finally statements are preserved; only its post-foreground call uses an owned explicit first-sample parser. After ACK and independent restoration, at most three read-only foreground samples qualify within 12 seconds, retaining the original 15-second command timeout and worker finally. Only the actual first explicit null focus permits waiting; ambiguous, foreign, malformed or failed observations stop. No input replay or reclassification of old04. Shared recorder, backend, adapter and helper remain unchanged. Full review-only INPUTS metadata is retained separately; operational guards remain in executable source. No runtime dispatched; whole-app qualification is false.\n').encode())
    print(json.dumps({'created':str(HERE),'flow_nonce':mapping['a14743fa3566f851b6724a54b0509744'],
        'only_local_source_preparation':True},sort_keys=True))

if __name__=='__main__':main()
