#!/usr/bin/env python3
"""Freeze only the reviewed Owner16 consumer delta; no runnable plan/request."""
import ast, difflib, hashlib, json
from pathlib import Path

W = Path(__file__).resolve().parent
F = W.parent / 'android-owner16-runtime-log-bounds-source-freeze02'


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def functions(raw):
    return {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(raw).body
            if isinstance(n, (ast.FunctionDef, ast.ClassDef))}


def main():
    F.mkdir(exist_ok=False)
    facts = {'schema': 1, 'ready_for_runtime': False,
             'reason': 'actual Host16 compile/ordinary and Android C16 artifacts plus a fresh exact plan still required',
             'new_response_limit': 1024 * 1024, 'new_actor_limit': 4 * 1024 * 1024,
             'legacy_non_diagnostic_response_limit': 256 * 1024,
             'generic_record_limit': 1024 * 1024,
             'full_runtime_collector_proposed_limit': 5 * 1024 * 1024,
             'production_rust_c_sources_changed': False, 'remote_executed': False}
    diff = ''
    for name in sorted(('owned.py', 'actor.py', 'coordinator.py')):
        old = (W / 'preimage' / name).read_text()
        new = (W / 'candidate' / name).read_text()
        diff += ''.join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                          fromfile='preimage/' + name, tofile='candidate/' + name))
        before, after = functions(old), functions(new)
        changed = [n for n in before if before[n] != after.get(n)]
        expected = {'owned.py': ['control'], 'actor.py': ['native_lmkd'], 'coordinator.py': ['run']}[name]
        assert changed == expected, (name, changed)
        facts.setdefault('changed_existing_definitions', {})[name] = changed
        for side in ('preimage', 'candidate'):
            (F / side).mkdir(exist_ok=True)
            (F / side / name).write_bytes((W / side / name).read_bytes())
    assert diff == (W / 'consumer.diff').read_text()
    owned_old = ast.parse((W / 'preimage/owned.py').read_text())
    owned_new = ast.parse((W / 'candidate/owned.py').read_text())
    co = next(n for n in owned_old.body if isinstance(n, ast.FunctionDef) and n.name == 'control')
    cn = next(n for n in owned_new.body if isinstance(n, ast.FunctionDef) and n.name == 'control')
    assert ast.dump(ast.Module(body=co.body[:-1], type_ignores=[])) == ast.dump(ast.Module(body=cn.body[:-1], type_ignores=[]))
    wo, wn = co.body[-1], cn.body[-1]
    assert ast.dump(wo.items[0]) == ast.dump(wn.items[0])
    assert ast.dump(ast.Module(body=wo.body[:7], type_ignores=[])) == ast.dump(ast.Module(body=wn.body[:-1], type_ignores=[]))
    facts['original_control_process_socket_inode_peer_send_prefix_ast_unchanged'] = True
    original_actor = (W / 'preimage/actor.py').read_text()
    candidate_actor = (W / 'candidate/actor.py').read_text()
    assert candidate_actor.replace('for number in (198, 199, 200, 201, 202):', 'for number in (198, 199, 200, 201):') == original_actor
    original_c = (W / 'preimage/coordinator.py').read_text()
    candidate_c = (W / 'candidate/coordinator.py').read_text()
    assert candidate_c.replace("owned.read_actor_result(Path(plan['state']) / 'actor-result.json')",
                               "owned.read_json(Path(plan['state']) / 'actor-result.json')") == original_c
    facts['actor_exact_fixed_fd202_addition_only'] = True
    facts['coordinator_exact_one_read_call_only'] = True
    facts['original_first_error_handshake_main_and_retirement_gates_unchanged'] = True
    (F / 'consumer.diff').write_text(diff)
    for relative in ('controls.py', 'log_bounds.fragment.py',
                     'local-control04/command-result.json', 'local-control04/stdout.log', 'local-control04/stderr.log',
                     'local-control02/command-result.json', 'local-control02/stdout.log', 'local-control02/stderr.log',
                     'local-control03/command-result.json', 'local-control03/stdout.log', 'local-control03/stderr.log',
                     'history-control01/observed-failure.json', 'history-control03/observed-socket-capability-failure.json'):
        target = F / relative; target.parent.mkdir(exist_ok=True)
        target.write_bytes((W / relative).read_bytes())
    result = json.loads((F / 'local-control04/stdout.log').read_text())
    command = json.loads((F / 'local-control04/command-result.json').read_text())
    assert command['returncode'] == 0 and command['joined'] and command['stderr']['bytes'] == 0 and result['success']
    assert pin((F / 'local-control04/stdout.log').read_bytes()) == command['stdout']
    facts['local_controls'] = {'groups': len(result['controls']), 'synthetic_logger_audit': True,
                              'real_memfd_and_regular_io': True, 'receive_stream_adapter_seam': True,
                              'unix_socket_and_peer_admission_executed': False, 'children_spawned_in_final_run': 0,
                              'prior_failures_preserved': ['missing Python seal constants', 'managed pidfd PID mismatch', 'AF_UNIX EPERM']}
    facts['bounds_proof'] = '6 fixed slots * 524288 hex bytes + original 1048576 non-log bytes = 4194304 actor hard bound'
    base = W.parent / 'lmkd-recovery-20261105-01/owner15-normal01-freeze-01/source'
    facts['original_unchanged_source_references'] = {name: pin((base / name).read_bytes())
                                                   for name in ('pinned_support.py', 'prepare.py', 'qualify.py')}
    facts['core_source_manifest'] = pin((W.parent / 'android-owner16-init-log-source-freeze01/SOURCE_PINS.json').read_bytes())
    (F / 'validation.json').write_text(json.dumps(facts, sort_keys=True, indent=2) + '\n')
    (F / 'README.md').write_text('''# Owner16 bounded diagnostic consumer source

Source-only delta. There is no executable runtime request, plan, new generation nonce, or device action in this package. The copied coordinator still contains the exact preimage Owner15 path constants; it is an input to the future actual-bound Owner16 generator, never a request to replay Owner15.

The paired new control receiver allows at most 1 MiB on the wire. Only the exact init-log observation, bound to its containing audit nonce and full captured-prefix SHA256, earns allowance for at most 512 KiB of hex. The rest of each wire response must still fit the original 256 KiB. Failed marker, failed capture, failed retirement and failed descriptor close remain visible; none is promoted to successful lifecycle evidence.

The dedicated actor-result reader has a 4 MiB hard limit and checks the exact original atomic_json serialization. Subtracting valid hex only in the six fixed response fields must leave at most the original 1 MiB. Six maximum hex copies plus the old record budget fit exactly within 4 MiB. MAX_RECORD and all unrelated records retain their old limit. The eventual exact runtime-result collector needs a separate 5 MiB bound; it is not implemented or dispatched here.

All existing functions are unchanged except the control receive tail, the coordinator's one actor-result read and the native LMKD inherited-FD tuple (new FD202 added). Existing process/socket credentials, source pins, Main fences, first error, handshake and retirement gates remain byte/AST equal as recorded in validation.json.

Final local controls use a real sealed, capacity-filled memfd, full serialized original-retained-record shape, actual owned-file reads and an explicit recv adapter seam. The six-copy actor is 3,244,236 bytes and corresponding coordinator 3,261,874 bytes; full value equality and original first_error are checked. Ten malformed-log cases plus original response/record limits are rejected. Local attempts to run the unchanged full Process/socket admission failed because of a managed pidfd PID mismatch and AF_UNIX EPERM; those actual failures are retained. They are not Android or producer qualifications. The final run spawned no child and does not claim the peer admission was executed.
''')
    (F / 'freeze.py').write_bytes(Path(__file__).read_bytes())
    rows = {str(path.relative_to(F)): pin(path.read_bytes()) for path in sorted(F.rglob('*')) if path.is_file()}
    (F / 'SOURCE_PINS.json').write_text(json.dumps(rows, sort_keys=True, indent=2) + '\n')
    print(json.dumps({'root': str(F), 'payload_files': len(rows), 'manifest': pin((F / 'SOURCE_PINS.json').read_bytes()),
                      'diff': pin(diff.encode()), 'control': command, 'validation': facts}, sort_keys=True))


if __name__ == '__main__':
    main()
