#!/usr/bin/env python3
"""Exact saved XML counter boundary tests; no Android operations or XML output."""
from pathlib import Path
import argparse, hashlib, importlib.util, json, re, symtable

ROOT=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture',type=Path,required=True)
    args=parser.parse_args()
    spec=importlib.util.spec_from_file_location('install_metadata_candidate',ROOT/'clock_install03.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    raw=args.fixture.read_bytes()
    assert hashlib.sha256(raw).hexdigest()=='2eb569d90fed2625825354851e9597905e191b5670e837a980a2b9d25e6c1745'
    def snapshot(data):
        return {'preferences_sha256':hashlib.sha256(data).hexdigest(),
            'preferences_metadata':module.preference_metadata(data)}
    pattern=rb'(<int name="intent\.extra\.alarm\.global\.id" value=")(-?[0-9]+)(" />)'
    found=list(re.finditer(pattern,raw));assert len(found)==1
    match=found[0];value=int(match[2]);assert value==120
    def changed(n):return raw[:match.start(2)]+str(n).encode()+raw[match.end(2):]
    before=snapshot(raw);rows=[]
    table=symtable.symtable((ROOT/'clock_install03.py').read_text(),'clock_install03.py','exec')
    actual_snapshot=[scope for scope in table.get_children() if scope.get_name()=='snapshot']
    assert len(actual_snapshot)==1
    assert actual_snapshot[0].lookup('preference_metadata').is_global()
    assert actual_snapshot[0].lookup('pref_meta').is_local()
    rows.append({'case':'actual_snapshot_helper_not_shadowed','passed':True})
    for label,data,expected in (
        ('identical_bytes',raw,True),('one_global_counter_increment',changed(121),True),
        ('counter_increment_two_rejected',changed(122),False),('counter_decrement_rejected',changed(119),False),
        ('other_xml_bytes_rejected',changed(121)+b'\n',False)):
        review=module.preference_review(before,snapshot(data));assert review['accepted'] is expected,label
        if label=='one_global_counter_increment':
            assert review['preferences_bytes_identical'] is False
            assert review['only_documented_global_intent_counter_increment'] is True
        rows.append({'case':label,'passed':True})
    assert module.preference_review({}, {})['accepted'] is False
    rows.append({'case':'missing_proof_rejected','passed':True})
    for label,data in (
        ('duplicate_counter_rejected',raw.replace(b'</map>',match[0]+b'\n</map>')),
        ('missing_counter_rejected',raw[:match.start()]+raw[match.end():]),
        ('counter_overflow_rejected',changed(2147483647))):
        try:module.preference_metadata(data)
        except RuntimeError:pass
        else:raise AssertionError(label)
        rows.append({'case':label,'passed':True})
    result={'state':'EXACT_COUNTER_METADATA_BOUNDARIES_PASS','count':len(rows),'cases':rows,
        'private_saved_fixture_sha256':hashlib.sha256(raw).hexdigest(),
        'source_sha256':hashlib.sha256((ROOT/'clock_install03.py').read_bytes()).hexdigest(),
        'private_XML_included':False,'Android_or_install_commands_executed':0}
    data=(json.dumps(result,indent=2,sort_keys=True)+'\n').encode()
    (ROOT/'install03-local-validation.json').write_bytes(data)
    print(json.dumps({'state':result['state'],'passed':len(rows),'result_sha256':hashlib.sha256(data).hexdigest()}))


if __name__=='__main__':main()
