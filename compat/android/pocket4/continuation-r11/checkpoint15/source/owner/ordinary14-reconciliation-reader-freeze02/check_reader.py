"""Local parser/owned-file controls; never scans the worker's real jobs root."""
from pathlib import Path
import copy
import hashlib
import json
import os
import tempfile
import time
import types

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'read_requests.py'
APPROVED = ROOT.parent / 'producer14-fixture-ordinary-freeze-01/request.json'


def main():
    source = SOURCE.read_bytes()
    approved_raw = APPROVED.read_bytes()
    assert hashlib.sha256(approved_raw).hexdigest() == 'd383190cf90e1d752e1fcc3de757c9c9cb9092e1646235ad33e40cd71d535fc6'
    approved = json.loads(approved_raw)
    m = types.ModuleType('owned_reader_controls')
    m.__file__ = str(SOURCE)
    exec(compile(source, str(SOURCE), 'exec'), m.__dict__)
    assert m.APPROVED == {key: approved.get(key, {}) for key in m.APPROVED}
    assert len(approved['stdin'].encode()) == m.APPROVED_STDIN_BYTES
    assert hashlib.sha256(approved['stdin'].encode()).hexdigest() == m.APPROVED_STDIN_SHA256
    results = []
    def check(name, predicate):
        assert predicate, name
        results.append(name)
    for suffix in ['1','12','123','1234']:
        check('observed_job_suffix_length_' + str(len(suffix)),
              m.JOB_ID.fullmatch('1a1ab000001-fc05-' + suffix) is not None)
    for index,bad in enumerate(['1a1ab000001-fc05-', '1a1ab000001-fc05-12345',
        '../1a1ab000001-fc05-1', '1a1ab000001-fc05-1/request.json',
        '1a1ab000001-fc05-g', '1a1ab000001-fc05-A',
        '1a1ab000001-fc05-1\n', '1a1ab000001-fc05-1\x00']):
        check('invalid_job_name_rejected_' + str(index),m.JOB_ID.fullmatch(bad) is None)
    check('exact_execution_tuple_accepted', m.tuple_matches(copy.deepcopy(m.APPROVED)))
    for key in m.APPROVED:
        value = copy.deepcopy(m.APPROVED)
        if type(value[key]) is int: value[key] += 1
        elif type(value[key]) is str: value[key] += '-changed'
        elif type(value[key]) is list: value[key] = value[key] + ['unexpected']
        else: value[key] = {'unexpected': 'value'}
        check('reject_changed_' + key, not m.tuple_matches(value))
    value = copy.deepcopy(m.APPROVED); value['cpu_quota_percent'] = True
    check('boolean_is_not_resource_integer', not m.tuple_matches(value))
    value = copy.deepcopy(m.APPROVED)
    for key in value:
        if type(value[key]) is int:value[key] = float(value[key])
    check('identical_integral_JSON_numbers_match_without_rounding',m.tuple_matches(value))
    for raw in [b'{"args":[],"args":[]}', b'[]', b'\xff']:
        try: m.request_object(raw)
        except m.MetadataError: pass
        else: raise AssertionError('invalid/duplicate JSON accepted')
    results.append('duplicate_nonobject_and_nonUTF8_rejected')
    fd_before = len(os.listdir('/proc/self/fd'))
    with tempfile.TemporaryDirectory(prefix='owned-only-', dir=ROOT) as temp:
        # These are local I/O seams, not a bypass reachable through main().
        m.JOBS = temp; m.EXPECTED_UID = os.getuid()
        def create(job_id, changed=False, stdin=None):
            directory = Path(temp) / job_id; directory.mkdir(mode=0o700)
            value = copy.deepcopy(m.APPROVED)
            if changed: value['nice'] += 1
            value.update(job_id=job_id, job_dir=str(directory), stdin_path=str(directory/'stdin.bin'),
                         request_digest='1'*64, request_fingerprint='1'*64)
            (directory/'request.json').write_text(json.dumps(value))
            (directory/'stdin.bin').write_bytes(approved['stdin'].encode() if stdin is None else stdin)
            return directory
        exact_id='1a1ab000001-fc05-0001'; changed_id='1a1ab000002-fc05-0002'
        exact=create(exact_id); create(changed_id, changed=True, stdin=b'NONMATCHING_STDIN_MUST_NOT_BE_READ')
        original=m.read_regular; reads=[]
        def observed(parent,name,maximum,state):
            reads.append((os.fstat(parent).st_ino,name))
            return original(parent,name,maximum,state)
        m.read_regular=observed
        state={'deadline':time.monotonic()+10,'read_bytes':0,'entries_seen':0,'requests_read':0,
               'nonmatching_requests':0,'unrecognized_names':0,'unreadable_or_rejected_counts':{},
               'matches':[],'close_errors':[],'enumeration_exhausted':False}
        fd=os.open(temp,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
        try: m.scan(fd,state)
        finally: os.close(fd)
        check('two_real_owned_metadata_files_scanned',state['enumeration_exhausted'] and state['requests_read']==2)
        check('exact_candidate_stdin_held_and_pinned',len(state['matches'])==1 and state['matches'][0]['job_id']==exact_id and state['matches'][0]['stdin_matches'] and state['matches'][0]['held_job_directory_stable'])
        check('nonmatching_stdin_never_opened',[x for x in reads if x[1]=='stdin.bin']==[(exact.stat().st_ino,'stdin.bin')])
        m.read_regular=original
        fd=os.open(exact,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
        try:
            (exact/'link.json').symlink_to('request.json')
            try: original(fd,'link.json',131072,state)
            except OSError as error: check('symlink_denied',error.errno==40)
            else: raise AssertionError('symlink followed')
            try: original(fd,'request.json',1,state)
            except m.BoundError: results.append('single_file_bound_rejected')
            else: raise AssertionError('file bound ignored')
            expired=dict(state,deadline=time.monotonic()-1)
            try: original(fd,'request.json',131072,expired)
            except m.BoundError: results.append('expired_read_opens_nothing')
            else: raise AssertionError('deadline ignored')
        finally: os.close(fd)
    check('local_owned_FDs_return_to_baseline',len(os.listdir('/proc/self/fd'))==fd_before)
    assert SOURCE.read_bytes()==source
    report={'schema':1,'scope':'Local exact-parser and two owned temporary metadata files only',
            'source_sha256':hashlib.sha256(source).hexdigest(),'approved_request_sha256':hashlib.sha256(approved_raw).hexdigest(),
            'controls_passed':len(results),'controls':results,'production_main_executed':False,
            'real_jobs_root_accessed':False,'ordinary14_or_Android_executed':False,
            'test_seams':['Only local module globals JOBS and EXPECTED_UID were redirected to the owned temporary directory/current local uid; production source unchanged','A local read_regular observer records file names/inodes solely in the synthetic fixture; no other user metadata was read'],
            'source_unchanged':True}
    raw=(json.dumps(report,sort_keys=True,indent=2)+'\n').encode()
    with (ROOT/'checks.json').open('xb') as f:f.write(raw)
    print(json.dumps({'controls':len(results),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}))


if __name__=='__main__':main()
