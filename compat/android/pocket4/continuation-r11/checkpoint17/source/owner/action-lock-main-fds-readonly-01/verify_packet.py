#!/usr/bin/env python3
"""Verify fixed local bytes and a PLAN-only wrapper variant; never collect."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import types

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'action-lock-owner-readonly-01'
IDENTITY = Path('/workspace/scratch/94990735b266/root-recovery-20261104-02/evidence/main-identity-readonly02/stdout.log')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(path):
    raw = path.read_bytes()
    raw.decode('utf-8', 'strict')
    return dict(path=path.name, bytes=len(raw), sha256=sha(raw),
                git_blob_sha1=hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest(),
                mode='100644', encoding='utf-8')


def put(name, value):
    raw = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode('ascii')
    with (HERE / name).open('xb') as stream:
        stream.write(raw)


def main():
    request_raw = (HERE / 'exact-request.json').read_bytes()
    request = json.loads(request_raw)
    packet_raw = (HERE / 'request-stdin.json').read_bytes()
    packet = json.loads(packet_raw)
    wrapper_raw = (HERE / 'wrapper.py').read_bytes()
    wrapper = wrapper_raw.decode()
    manifest = json.loads((HERE / 'source-manifest.json').read_bytes())
    assert set(packet) == {'schema', 'files'} and packet['schema'] == 1
    assert set(packet['files']) == {x['path'] for x in manifest['files']} and len(packet['files']) == 3
    for row in manifest['files']:
        body = (HERE / row['path']).read_bytes()
        assert row == pin(HERE / row['path'])
        assert body == packet['files'][row['path']].encode('utf-8')
    assert request['stdin'].encode('utf-8') == packet_raw
    assert request['args'] == ['-n', '/usr/bin/python3', '-I', '-B', '-c', wrapper]
    assert request['host'] == 'pocket4' and request['executable'] == '/usr/bin/sudo' and request['cwd'] == '/'
    assert request['env'] == {'PYTHONDONTWRITEBYTECODE': '1'}
    assert (request['cpu_quota_percent'], request['memory_max_bytes'], request['nice'], request['timeout_seconds']) == (100,134217728,10,30)
    assert request['idempotency_key'] == 'p4-action-lock-main-fds-readonly01-' + sha(packet_raw)[:16]
    assert len(packet_raw) <= 131072 and 'raw = sys.stdin.buffer.read(131073)' in wrapper
    assert str(len(packet_raw)) in wrapper and repr(sha(packet_raw)) in wrapper
    for name in ('read_main_lock_fds.py', 'read_main_identity.py', 'check_controls.py', 'make_request.py', 'wrapper.py'):
        ast.parse((HERE / name).read_bytes())
    assert (HERE/'read_main_identity.py').read_bytes() == (OLD/'read_main_identity.py').read_bytes()
    source = (HERE / 'read_main_lock_fds.py').read_bytes()
    tree = ast.parse(source)
    functions = {node.name: node for node in tree.body if isinstance(node, (ast.FunctionDef,ast.ClassDef))}
    old_functions = {node.name: node for node in ast.parse((OLD/'read_lock_owner.py').read_bytes()).body
                     if isinstance(node, (ast.FunctionDef,ast.ClassDef))}
    same = ('need','sha','error_record','parse_proc_stat','identity_key','open_lock_metadata')
    assert all(ast.dump(functions[n],include_attributes=False) == ast.dump(old_functions[n],include_attributes=False) for n in same)
    prohibited = {'flock','lockf','pidfd_getfd','pidfd_send_signal','kill','killpg','sendmsg','recvmsg',
                  'socket','Popen','fork','posix_spawn','execve','execv','setns','unshare','write','pwrite',
                  'rename','replace','unlink','remove','mkdir','rmdir'}
    calls = {(node.func.value.id,node.func.attr) for node in ast.walk(tree)
             if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name)}
    forbidden_calls = {call for call in calls if call[0] in ('os','fcntl','socket','subprocess') and call[1] in prohibited}
    assert not forbidden_calls, sorted(forbidden_calls)
    identity_raw = IDENTITY.read_bytes()
    assert (len(identity_raw),sha(identity_raw)) == (23171,'e9344b538fbf6f6f06442b27d81d772be40db0ee3f3805823648a0a733055116')
    identity = json.loads(identity_raw)
    assert identity['collection_complete'] is True and identity['original_guard']['passed'] is True
    module = types.ModuleType('local_packet_reader_verification')
    exec(compile(source,str(HERE/'read_main_lock_fds.py'),'exec'),module.__dict__)
    support = types.ModuleType('local_packet_support_verification')
    exec(compile((HERE/'read_main_identity.py').read_bytes(),str(HERE/'read_main_identity.py'),'exec'),support.__dict__)
    actual = {name: row['actual'] for name,row in identity['phases'][0]['processes'].items()}
    activation_shape = {'framework_epoch': {'binding': {'processes': {n:actual[n] for n in support.FRAMEWORK_ROLES}}}}
    activation_shape.update({n:actual[n] for n in support.HOST_ROLES})
    assert module.expected_processes(activation_shape,support) == actual
    module.validate_prior((HERE/'prior-ticket-launch.json').read_bytes())
    assert wrapper.count("['--collect-once']") == 1
    plan_wrapper = wrapper.replace("['--collect-once']", '[]')
    result = subprocess.run(['/usr/bin/python3','-I','-B','-c',plan_wrapper],input=packet_raw,
                            capture_output=True,cwd='/',timeout=10,check=False)
    assert result.returncode == 0 and not result.stderr
    plan = json.loads(result.stdout)
    assert plan['state'] == 'PLAN_ONLY' and plan['remote_actions'] == 0 and plan['runtime_authorized'] is False
    for name,body in [('plan.stdout.json',result.stdout),('plan.stderr.txt',result.stderr)]:
        with (HERE/name).open('xb') as stream:
            stream.write(body)
    value = dict(schema=1, passed=True, request=pin(HERE/'exact-request.json'), stdin=pin(HERE/'request-stdin.json'),
                 wrapper=pin(HERE/'wrapper.py'), source=pin(HERE/'read_main_lock_fds.py'), runtime_members=manifest['files'],
                 inherited_helper_AST_equal=list(same), original_support_byte_identical=True,
                 retained_identity=dict(path=str(IDENTITY),bytes=len(identity_raw),sha256=sha(identity_raw)),
                 exact_seven_PID_birth_and_identity_schema_match_retained_actual=True,
                 retained_identity_is_not_a_new_live_observation=True,
                 packet_members_and_request_stdin_byte_identical=True, explicit_resources_match=True,
                 default_PLAN_actual_exit=result.returncode, PLAN_stdout=pin(HERE/'plan.stdout.json'),
                 PLAN_used_only_collect_argument_replacement=True, collect_executed=False,
                 no_remote_calls=True, live_proc_Main_reads=False, qualification=False)
    put('packet-validation.json',value)
    print(json.dumps(dict(passed=True,request=pin(HERE/'exact-request.json'),stdin=pin(HERE/'request-stdin.json'),
                          wrapper=pin(HERE/'wrapper.py'),validation=pin(HERE/'packet-validation.json'),
                          idempotency_key=request['idempotency_key']),sort_keys=True))


if __name__ == '__main__':
    main()
