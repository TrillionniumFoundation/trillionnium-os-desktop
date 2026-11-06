#!/usr/bin/env python3
"""Keep r1 intact; bind the new helper's guest staging to its new state nonce."""
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    source = HERE / 'candidate-r1/helper'
    output = HERE / 'candidate-r2/helper'
    raw = (source / 'SOURCE_PINS.json').read_bytes()
    assert len(raw) == 3031 and sha(raw) == '464400297c71022c9f8554ebe6588f1cd5a69ae0874c2ce556fa0627e8349b84'
    manifest = json.loads(raw)
    files = {}
    for name, pin in manifest['files'].items():
        body = (source / name).read_bytes()
        assert pin == {'bytes': len(body), 'sha256': sha(body)}
        files[name] = body
    name = 'install_owned_helper.py'
    before = files[name].decode()
    old = "        stage = Stage(held.target,args.flow_dir.name.rsplit('-',1)[1])"
    new = "        stage = Stage(held.target,args.state_nonce)"
    assert before.count(old) == 1
    after = before.replace(old, new)
    files[name] = after.encode()
    manifest['files'][name] = {'bytes':len(files[name]),'sha256':sha(files[name])}
    manifest['new_guest_stage_nonce_source'] = 'fresh exact install state_nonce; old flow can be preserved without guest stage path reuse'
    manifest['unsubmitted_parent_candidate_sha256'] = sha(raw)
    final = json.dumps(manifest,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()+b'\n'
    output.mkdir(parents=True)
    for relative, body in files.items():
        path=output/relative;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as handle:handle.write(body)
    with (output/'SOURCE_PINS.json').open('xb') as handle:handle.write(final)
    patch=''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),
                                    fromfile='candidate-r1/helper/'+name,tofile='candidate-r2/helper/'+name))
    with (output.parent/'AGAINST_R1.patch').open('w') as handle:handle.write(patch)
    old_plan=json.loads((HERE/'candidate-r1/REVIEW_PLAN.json').read_bytes())
    old_plan['helper_source_manifest_bytes']=len(final);old_plan['helper_source_manifest_sha256']=sha(final)
    old_plan['build_argv_after_reviewed_stage'][-1]=sha(final)
    old_plan['guest_stage_nonce_source']='fresh state_nonce; strict new guest directory, no existing file replacement'
    for row in old_plan['changed_files']:
        if row['new_path']==name:
            row.update(new_bytes=len(files[name]),new_sha256=sha(files[name]))
    with (output.parent/'REVIEW_PLAN.json').open('w') as handle:json.dump(old_plan,handle,indent=2,sort_keys=True);handle.write('\n')
    report={'schema':'pocket4-fixed-search-r2-guest-stage-revision-v1','old_candidate_manifest_sha256':sha(raw),
            'new_candidate_manifest_bytes':len(final),'new_candidate_manifest_sha256':sha(final),
            'only_helper_source_change':'install_owned_helper.execute: Stage nonce changes from old flow nonce to new state_nonce',
            'unchanged_helper_source_files':sorted(set(files)-{name}),
            'existing_controls_reused_only_for_byte_identical_inputs':True,'remote_execution_attempted':False,
            'r1_unsubmitted_preserved':True,'production_ready':False}
    with (output.parent/'REVISION_PROOF.json').open('w') as handle:json.dump(report,handle,indent=2,sort_keys=True);handle.write('\n')
    print(json.dumps(report,sort_keys=True))


if __name__ == '__main__':
    main()
