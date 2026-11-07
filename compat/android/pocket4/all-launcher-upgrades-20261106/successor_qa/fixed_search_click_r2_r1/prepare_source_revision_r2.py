#!/usr/bin/env python3
"""Correct post-action failure attribution without changing guard predicates."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parents[1]
PARENT=HERE/'source-r1'
OUT=HERE/'source-r2'


def pin(path):
    raw=path.read_bytes()
    return {'path':str(path.relative_to(PROJECT)), 'bytes':len(raw), 'sha256':hashlib.sha256(raw).hexdigest()}


def main():
    source_path=PARENT/'owned_fixed_search_click_once.py'
    source=source_path.read_text()
    assert pin(source_path)['sha256']=='4cafb3d27333275a00cb36323ade37fc60d7c41c9e80d9a300e42893f79f8cb8'
    replacements={
        'def whole_scope_guard(base, core):':'def whole_scope_guard(base, core, *, action_attempted=False):',
        'typed = guard.current_guard(action_attempted=False)':'typed = guard.current_guard(action_attempted=action_attempted)',
        "result['whole_scope_after'] = whole_scope_guard(base, core)":"result['whole_scope_after'] = whole_scope_guard(base, core, action_attempted=original['action_attempted'])",
    }
    revised=source
    for old,new in replacements.items():
        assert revised.count(old)==1,old
        revised=revised.replace(old,new)
    compile(revised,str(OUT/'owned_fixed_search_click_once.py'),'exec')
    OUT.mkdir(exist_ok=False)
    (OUT/'owned_fixed_search_click_once.py').write_text(revised)
    (OUT/'SOURCE_DIFF_FROM_R1.patch').write_text(''.join(difflib.unified_diff(source.splitlines(True),revised.splitlines(True),
        fromfile=str(source_path.relative_to(PROJECT)),tofile=str((OUT/'owned_fixed_search_click_once.py').relative_to(PROJECT)))))
    readonly=PROJECT/'successor_qa/search_helper_readonly_inspect_r1/candidate-r1/owned_readonly_inspect_once.py'
    (OUT/'SOURCE_DIFF_FROM_READONLY.patch').write_text(''.join(difflib.unified_diff(readonly.read_text().splitlines(True),revised.splitlines(True),
        fromfile=str(readonly.relative_to(PROJECT)),tofile=str((OUT/'owned_fixed_search_click_once.py').relative_to(PROJECT)))))
    prep=json.loads((PARENT/'PREPARATION.json').read_bytes())
    prep.update(source=pin(OUT/'owned_fixed_search_click_once.py'),
        parent_source_revision=pin(source_path),
        correction='Additional full49 typed post-guard now receives the already verified original action_attempted flag. Underlying guard predicates/return fields/budgets remain unchanged; only post-action failure attribution is corrected. Before-guard remains false. Both revisions unexecuted.',
        changed_original_functions=['entry','outer_request','declared_request','verify_original','whole_scope_guard','child','parent'])
    prep['unchanged_original_functions'].remove('whole_scope_guard')
    (OUT/'PREPARATION.json').write_text(json.dumps(prep,sort_keys=True,indent=2)+'\n')
    inputs=[Path(__file__),source_path,PARENT/'PREPARATION.json',readonly,
        PROJECT/'recovery/successor_runtime.py',PROJECT/'recovery/independent_repair_r2/actual-execute-01/current_baseline_guard.py']
    m={'schema':'pocket4-fixed-search-unbound-source-pins-v1','inputs':[pin(p) for p in inputs],
       'outputs':[pin(p) for p in sorted(OUT.iterdir()) if p.is_file()],
       'source_entry_disabled':True,'execution_request_created':False,'no_remote_or_UI_operation':True}
    (OUT/'SOURCE_PINS.json').write_text(json.dumps(m,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'status':'SOURCE_ONLY_POST_ACTION_ATTRIBUTION_CORRECTED','source':pin(OUT/'owned_fixed_search_click_once.py'),
        'minimal_diff':pin(OUT/'SOURCE_DIFF_FROM_R1.patch'),'manifest':pin(OUT/'SOURCE_PINS.json'),
        'previous_source_retained':True,'request_created':False,'Android_actions':0},sort_keys=True))


if __name__=='__main__':main()
