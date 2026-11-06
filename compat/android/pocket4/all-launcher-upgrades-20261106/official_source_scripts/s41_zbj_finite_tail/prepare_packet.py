#!/usr/bin/env python3
"""Assemble S41 from exact existing sources/receipts; never submit or download."""
from pathlib import Path
import ast
import copy
import difflib
import hashlib
import json
import pprint

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent
BASE = PROJECT / 'official_source_scripts/s34_zbj_tail'
S36 = PROJECT / 'official_source_scripts/s36_szzc_finite_tail'
S40 = PROJECT / 'official_source_scripts/s40_zbj_dns_probe'
READBACK = PROJECT / 'reference/rail-zbj-delivery-research-r1/receipt-readback-r1'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(path):
    raw = path.read_bytes()
    return {'path': str(path.relative_to(PROJECT)), 'bytes': len(raw), 'sha256': digest(raw)}


def exact(path, sha=None):
    raw = path.read_bytes()
    if sha is not None:
        assert digest(raw) == sha, (str(path), digest(raw), sha)
    return raw


def write_new(name, raw):
    if isinstance(raw, str):
        raw = raw.encode()
    path = HERE / name
    if path.exists():
        assert path.read_bytes() == raw, ('FROZEN_OUTPUT_DIFFERS', name)
    else:
        with path.open('xb') as stream:
            stream.write(raw)
    return pin(path)


def write_json(name, value):
    return write_new(name, json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def replace_once(text, old, new):
    assert text.count(old) == 1, ('EXACT_REPLACEMENT_REQUIRED', old[:160], text.count(old))
    return text.replace(old, new, 1)


def functions(text):
    return {node.name: ast.get_source_segment(text, node) for node in ast.parse(text).body
            if isinstance(node, ast.FunctionDef)}


base = exact(BASE / 'resume_zbj_tail_s34_once.py').decode()
base_functions = functions(base)
extension = exact(HERE / 'extensions.py').decode()
extra_functions = functions(extension)
s36 = exact(S36 / 'continue_szzc_once.py').decode()
census = functions(s36)['census']
authority_raw = exact(BASE / 'actual-r1/com.zhubajie.client-result.raw.json',
    'c49b3c374226329c92810d11bacee29c75023c26bf648bf5c4a6ebf7ea741135')
authority = json.loads(authority_raw)
s34_info = json.loads((BASE / 'actual-r1/result.file-info.raw.json').read_bytes())
s34_failure_info = json.loads((BASE / 'actual-r1/range-0003.file-info.raw.json').read_bytes())
assert (s34_info['size'], s34_info['sha256']) == (65232, digest(authority_raw))
s34_result_pin = {key: s34_info[key] for key in ('path', 'sha256')}
s34_result_pin['bytes'] = s34_info['size']
s34_failure_pin = authority['segment_receipts'][3]['receipt']
assert (s34_failure_info['path'], s34_failure_info['size'], s34_failure_info['sha256']) == (
    s34_failure_pin['path'], s34_failure_pin['bytes'], s34_failure_pin['sha256'])
readback_raw = exact(READBACK / 'verification.json',
    'b4a65754c4c39931b821458c08de049ecf5421b2de28b531c2c4708e79981882')
readback = json.loads(readback_raw)
assert readback['all_ns_exact'] and readback['receipts_read'] == 3 and readback['body_file_info_only'] == 3
exact_identities = {}
for info in (s34_info, s34_failure_info):
    exact_identities[info['path']] = {'bytes': info['size'], 'mode': info['mode'], 'version': info['version']}
s34_receipt_pins, s34_body_pins = [], []
for index in range(3):
    declaration = authority['segment_receipts'][index]['receipt']
    raw = exact(READBACK / f'receipt-{index:04d}.original.json', declaration['sha256'])
    assert len(raw) == declaration['bytes']
    item = json.loads(raw)
    receipt_info = json.loads((READBACK / f'receipt-{index:04d}.file-info.content-0.original.txt').read_bytes())
    body_info = json.loads((READBACK / f'body-{index:04d}.file-info.content-0.original.txt').read_bytes())
    assert receipt_info['path'] == declaration['path'] and receipt_info['sha256'] == declaration['sha256']
    assert body_info['path'] == item['path'] and body_info['sha256'] == item['sha256'] and body_info['size'] == item['bytes']
    assert body_info['version'] == ':'.join(str(item['stat'][key]) for key in (
        'st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))
    assert type(item['stat']['st_mtime_ns']) is int and type(item['stat']['st_ctime_ns']) is int
    for info in (receipt_info, body_info):
        exact_identities[info['path']] = {'bytes': info['size'], 'mode': info['mode'], 'version': info['version']}
    s34_receipt_pins.append(declaration)
    s34_body_pins.append({key: item[key] for key in ('path', 'bytes', 'sha256', 'stat')})

s28_terminal = exact(BASE / 'actual-s28-terminal.json', '4274659d373393b89ee65ed999be21db790a1a464895f8a8283cffe8f18e5030')
s34_terminal = exact(BASE / 'actual-r1/terminal.raw.json', 'e10d132f8089f20add7a403ff05bd31620fd785ab8f7db934817bdae797ba239')
dns_terminal = exact(S40 / 'actual/status-01.original.txt', '7b06805ce07faf432aedcef9deec25571d4069ca668ed76c640de9205dd70fb0')
dns_stdout = exact(S40 / 'actual/stdout.original.jsonl', '61ecdfd852260204ef324d4fbd518eae55f9e9660bd7788bce110f6f99173c95')
assert exact(S40 / 'actual/stderr.original.txt') == b''

source = replace_once(base, 'One explicit s34 tail after settled s28: 41 sequential ranges, at most 1 MiB.',
    'One explicit s41 tail after settled s34 and DNS observation: 38 sequential ranges, at most 1 MiB.')
source = replace_once(source, 'Only the original prefix and COMPLETE s28 segments 0..40 are reused.',
    'Reuse the original prefix, COMPLETE s28 segments 0..40 and COMPLETE s34 segments 0..2.')
source = replace_once(source, 'import datetime\n', 'import datetime\nimport fcntl\nimport sys\n')
source = replace_once(source, "ROOT=Path('/home/alex/work/pocket4-launcher-official-candidates-20261106-zbj-tail-s34')",
    "ROOT=Path('/home/alex/work/pocket4-launcher-official-candidates-20261106-zbj-tail-s41')")
source = replace_once(source, 'TAIL_START=124370944\n', 'TAIL_START=127516672\n')

constants = {
    'OLD_TAIL_START': 124370944,
    'S34_PREFIX_SHA256': 'b5afd036ee69dda692bc5e20a35ddd38c66431ce7704960e7bac3b6f2a3f2584',
    'S34_FOLDER': '/home/alex/work/pocket4-launcher-official-candidates-20261106-zbj-tail-s34/com.zhubajie.client-tail-1m',
    'S34_RESULT_PIN': s34_result_pin, 'S34_FAILURE_PIN': s34_failure_pin,
    'S34_COMPLETE_RECEIPTS': s34_receipt_pins, 'S34_BODY_PINS': s34_body_pins,
    'EXACT_RECENT_IDENTITIES': exact_identities, 'PARENT_IDENTITIES': {},
    'S28_TERMINAL_RAW': s28_terminal.decode(), 'S28_TERMINAL_SHA256': digest(s28_terminal),
    'S34_TERMINAL_RAW': s34_terminal.decode(), 'S34_TERMINAL_SHA256': digest(s34_terminal),
    'DNS_TERMINAL_RAW': dns_terminal.decode(), 'DNS_TERMINAL_SHA256': digest(dns_terminal),
    'DNS_STDOUT_RAW': dns_stdout.decode(), 'DNS_STDOUT_SHA256': digest(dns_stdout),
}
constant_source = '\n'.join(name + '=' + pprint.pformat(value, sort_dicts=False, width=120)
                            for name, value in constants.items()) + '\n'
source = replace_once(source, base_functions['now'], constant_source + '\n' + base_functions['now'])
source = replace_once(source, base_functions['opened'], extra_functions['opened'])
source = replace_once(source, base_functions['main'], extra_functions['main'])

owned = base_functions['own_curl']
owned = replace_once(owned, 'owned_curl_signal_count=0,outcome_unknown=False,timed_out=False)',
    'owned_curl_signal_count=0,outcome_unknown=False,timed_out=False,owned_object_fallback_used=False)')
owned = replace_once(owned, '    process=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=met,stderr=err,pass_fds=(fd,),close_fds=True)',
    "    require(seconds>=1 and remaining()>=seconds+10,'OWNED_CURL_FRESH_BUDGET_BEFORE_SPAWN')\n"
    '    process=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=met,stderr=err,pass_fds=(fd,),close_fds=True)')
owned = replace_once(owned, '     try:process.wait(timeout=10);record.update(joined=True,returncode=process.returncode)',
    '     if process.returncode is None and pidfd is None:\n'
    '      # The direct, unreaped child is still owned by this Popen object.\n'
    '      # Retire it if acquiring a pidfd failed; this path can never pass.\n'
    "      record['owned_object_fallback_used']=True\n"
    "      try:process.kill();record['owned_curl_signal_count']+=1\n"
    '      except ProcessLookupError:pass\n'
    "      except BaseException as e:record['signal_error']=type(e).__name__\n"
    '     try:process.wait(timeout=10);record.update(joined=True,returncode=process.returncode)')
source = replace_once(source, base_functions['own_curl'], owned)

tail_plan = replace_once(base_functions['tail_plan'], 'len(ranges)==41 and sum(end-start+1 for _,start,end in ranges)==42502678',
    'len(ranges)==38 and sum(end-start+1 for _,start,end in ranges)==39356950')
source = replace_once(source, base_functions['tail_plan'], tail_plan)
one_segment = replace_once(base_functions['one_segment'], "'range_namespace':'S34_TAIL_1M_NO_CACHE'",
    "'range_namespace':'S41_TAIL_1M_NO_CACHE'")
source = replace_once(source, base_functions['one_segment'], one_segment)

run = base_functions['run']
run = replace_once(run, "strategy='one explicit s34 tail; old prefix+41 complete 2MiB segments; 41 sequential <=1MiB requests; no retries'",
    "strategy='one explicit s41 tail; old prefix+41 complete 2MiB segments+3 complete S34 1MiB segments; 38 sequential <=1MiB requests; no retries',\n"
    "          prior_jobs=c['prior_jobs']+['1a1b19cedcf-fc05-79de','1a1b2983a9d-fc05-7ed3']")
run = replace_once(run, '  prefix_segments=load_verified_prefix(c);row[\'verified_old_complete_segments\']=41',
    "  prefix_segments=load_verified_prefix(c);row['verified_old_complete_segments']=41\n"
    "  s34_segments=load_s34_complete(c,prefix_segments);row['verified_s34_complete_segments']=3\n"
    "  row['failed_s34_empty_partial_not_reused']=True;row['observed_prior_sources']=[]")
run = replace_once(run, "  c['expected_etags']=header_etags(text)",
    "  c['expected_etags']=header_etags(text)\n"
    "  require(c['expected_etags']==[],'ACTUAL_PRIOR_SOURCE_HAS_NO_SERVER_ETAG')")
run = replace_once(run, "                    'server_supplied_validator':bool(c['expected_etags'])}",
    "                    'server_supplied_validator':False,'entity_continuity_proven_by_etag':False}")
run = replace_once(run, "                                'receipt_chain':s['receipt_chain'],'prior_index':s['prior_index']} for s in prefix_segments]",
    "                                'receipt_chain':s['receipt_chain'],'prior_index':s['prior_index']} for s in prefix_segments]\n"
    "  sources.extend({'path':s['path'],'bytes':s['bytes'],'sha256':s['sha256'],'stat':s['stat'],\n"
    "                  'receipt_chain':s['receipt_chain'],'prior_s34_index':s['prior_s34_index']} for s in s34_segments)")
run = replace_once(run, '    copied=0\n',
    "    row['observed_prior_sources'].append({'path':d['path'],'bytes':d['bytes'],'sha256':d['sha256'],\n"
    "            'observed_stat':before,'historical_full_stat_pin_present':'stat' in d})\n"
    "    if count==OLD_TAIL_START:\n"
    "     require(h.hexdigest()==S34_PREFIX_SHA256,'RECONSTRUCTED_S34_PREFIX_CHANGED')\n"
    "     row['reconstructed_s34_prefix_sha256']=h.hexdigest()\n"
    '    copied=0\n')
run = replace_once(run, "   require(count==TAIL_START==OLD_PREFIX+41*OLD_CHUNK,'EXACT_NEW_TAIL_START_REQUIRED')",
    "   require(count==TAIL_START==OLD_PREFIX+41*OLD_CHUNK+3*CHUNK and\n"
    "           row.get('reconstructed_s34_prefix_sha256')==S34_PREFIX_SHA256,'EXACT_NEW_TAIL_START_REQUIRED')")
run = replace_once(run, "              'range_namespace':'S34_TAIL_1M_NO_CACHE','old_index_namespace':'S28_PREFIX_2M',",
    "              'range_namespace':'S41_TAIL_1M_NO_CACHE','old_index_namespace':'S28_PREFIX_2M',\n"
    "              's34_prefix_index_namespace':'S34_TAIL_1M_NO_CACHE',")
run = replace_once(run, "  require(load_verified_prefix(c)==prefix_segments,'PRIOR_RECEIPT_CHAIN_CHANGED')",
    "  require(load_verified_prefix(c)==prefix_segments,'PRIOR_RECEIPT_CHAIN_CHANGED')\n"
    "  require(load_s34_complete(c,prefix_segments)==s34_segments,'S34_RECEIPT_CHAIN_CHANGED')")
run = replace_once(run,
    "  final=ROOT/(c['package']+'.apk');require(not final.exists(),'FINAL_PATH_EXISTS');os.rename(part,final)\n"
    '  directory=os.open(ROOT,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)\n'
    '  try:os.fsync(directory)\n'
    '  finally:os.close(directory)',
    "  final=ROOT/(c['package']+'.apk')\n"
    '  directory=os.open(ROOT,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)\n'
    '  try:\n'
    "   require(os.fstat(directory).st_uid==1000 and stat.S_IMODE(os.fstat(directory).st_mode)==0o700,'NEW_PRIVATE_PUBLICATION_ROOT')\n"
    '   os.link(part.name,final.name,src_dir_fd=directory,dst_dir_fd=directory,follow_symlinks=False)\n'
    '   os.unlink(part.name,dir_fd=directory);os.fsync(directory)\n'
    '  finally:os.close(directory)')
run = replace_once(run, "                                    'greater_than_installed_code':369,'vendor_signature':True,'ABI':True})",
    "                                    'greater_than_historical_installed_code':369,'vendor_signature':True,'ABI':True,\n"
    "                                    'whole_APK_v2_or_v3_signature':True,'fresh_current_scope_before_install':True,\n"
    "                                    'historical_vendor_signer_sha256':'556246aaaf05f61c8bbb9587dfc0660e01f6c3c6813ec038d18684d3ab378bbe'},\n"
    "             outer_process_closure_success_also_required=True,partial_or_complete_candidate_installable=False)")
source = replace_once(source, base_functions['run'], run)

append_functions = [census] + [body for name, body in extra_functions.items() if name not in ('opened', 'main')]
source = replace_once(source, "if __name__=='__main__':raise SystemExit(main())",
    '\n\n'.join(append_functions) + "\n\nif __name__=='__main__':raise SystemExit(main())")
ast.parse(source)
compile(source, 'continue_zbj_s41_once.py', 'exec')
final_functions = functions(source)
unchanged = [name for name, body in base_functions.items() if final_functions[name] == body]
changed = [name for name, body in base_functions.items() if final_functions[name] != body]
assert changed == ['opened', 'own_curl', 'tail_plan', 'one_segment', 'run', 'main']
assert final_functions['census'] == census
base_tree = ast.parse(base); final_tree = ast.parse(source)
base_candidates = next(ast.literal_eval(node.value) for node in base_tree.body if isinstance(node, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == 'CANDIDATES' for t in node.targets))
final_candidates = next(ast.literal_eval(node.value) for node in final_tree.body if isinstance(node, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == 'CANDIDATES' for t in node.targets))
assert final_candidates == base_candidates
base_argv = next(ast.dump(node.value) for node in ast.walk(ast.parse(base_functions['one_segment']))
                 if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'argv' for t in node.targets))
final_argv = next(ast.dump(node.value) for node in ast.walk(ast.parse(final_functions['one_segment']))
                  if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'argv' for t in node.targets))
assert base_argv == final_argv
assert 'If-Range' not in source and '--resolve' not in source and 'ssl.create_default_context' not in source
source_ref = write_new('continue_zbj_s41_once.py', source)
diff_ref = write_new('against-S34.diff', ''.join(difflib.unified_diff(base.splitlines(True), source.splitlines(True),
    fromfile='S34/resume_zbj_tail_s34_once.py', tofile='S41/continue_zbj_s41_once.py')))
request = {
    'host': 'pocket4', 'executable': '/usr/bin/python3',
    'args': ['-I', '-B', '-c', source, '--continue-zbj-38-ranges-once'],
    'cwd': '/home/alex/work',
    'idempotency_key': 'pocket4-zbj-finite-tail-s41-20261106-r1',
    'cpu_quota_percent': 100, 'memory_max_bytes': 536870912,
    'nice': 10, 'timeout_seconds': 2100,
}
assert len(source.encode()) < 120000
request_ref = write_json('process-request.json', request)
inheritance_ref = write_json('inheritance.json', {
    'schema': 'pocket4-zbj-s41-source-inheritance-v1',
    'base_source': pin(BASE / 'resume_zbj_tail_s34_once.py'),
    'S34_functions_byte_unchanged': unchanged,
    'S34_functions_changed': changed,
    'S34_CANDIDATES_literal_equal': True,
    'S34_curl_argv_AST_equal': True,
    'S36_exact_function': {'source': pin(S36 / 'continue_szzc_once.py'), 'function': 'census', 'byte_equal': True},
    'S36_concepts_reimplemented_not_claimed_byte_equal': [
        'Walk existing parent directories with O_NOFOLLOW and preserve parent identity.',
        'Explicit full identity and hash recheck before and after reuse.',
        'Publish own new completed candidate using exclusive hardlink then remove only its own temporary name.',
        'Require complete original self-FD census restoration for success.'
    ],
    'S36_network_transport_used': False,
    'S36_actual_network_implementation': 'urllib with default verified HTTPS, no curl child',
    'pidfd_acquisition_failure_fix': 'If pidfd_open fails after Popen, kill/wait only that direct owned unreaped Popen child. Mark fallback; never treat that path as success. Original numeric or external PIDs are never targeted.',
    'fresh_spawn_budget_fix': 'Require remaining budget >= requested curl timeout+10 immediately before each Popen.',
    'no_server_ETag': True, 'fabricated_If_Range': False,
    'remote_execution_in_this_preparation': False,
})
plan_ref = write_json('execution-plan.json', {
    'schema': 'pocket4-zbj-s41-finite-tail-plan-v1',
    'state': 'SEALED_FOR_REVIEW_NOT_EXECUTED',
    'request': request_ref, 'source': source_ref, 'diff': diff_ref,
    'source_inheritance': inheritance_ref,
    'official_original_URL_preserved': base_candidates[0]['url'],
    'previous_result': pin(BASE / 'actual-r1/com.zhubajie.client-result.raw.json'),
    'previous_failure': pin(BASE / 'actual-r1/range-0003.raw.json'),
    'previous_terminal': pin(BASE / 'actual-r1/terminal.raw.json'),
    'latest_three_segment_readback': pin(READBACK / 'verification.json'),
    'actual_DNS_success': {'terminal': pin(S40 / 'actual/status-01.original.txt'),
                           'stdout': pin(S40 / 'actual/stdout.original.jsonl'),
                           'not_HTTP_or_future_DNS_proof': True},
    'new_host_root': '/home/alex/work/pocket4-launcher-official-candidates-20261106-zbj-tail-s41',
    'reused_inputs': {'original_prefix_bytes': 38387712, 'S28_complete_2MiB_segments': 41,
                      'S34_complete_1MiB_segments': 3, 'complete_prefix_bytes': 127516672,
                      'S28_failed_partial_reused': False, 'S34_failed_empty_partial_reused': False},
    'old_prefix_sha_gate': 'The reconstructed first124370944B must equal the actual S34 prefix SHA b5afd036ee69dda692bc5e20a35ddd38c66431ce7704960e7bac3b6f2a3f2584.',
    'old_identity_policy': 'Retain exact recorded full stat for existing complete bodies. Bind latest file_info versions for S34 result/failure/three receipts/three bodies. Older metadata without historical inode pins retain their original size/full-SHA/UID regular-file contract, capture current identity, and recheck; no historical inode is invented.',
    'network_tail': {'start': 127516672, 'end': 166873621, 'bytes': 39356950,
                     'ranges': 38, 'max_range_bytes': 1048576, 'last_range_bytes': 559638,
                     'concurrency': 1, 'attempts_each': 1, 'application_retries': 0,
                     'spacing_seconds': 2, 'total_deadline_seconds': 1800,
                     'curl_per_range_max_seconds': 180},
    'HTTPS_contract': 'Original S34 curl executable/arguments and UA. Normal DNS, required TLS certificate verification, HTTPS only, no redirects, exact206 and Content-Range, exact length, no automatic retry. HTTP403/429/Retry-After and any transfer/identity failure stop further requests.',
    'ETag_contract': 'Actual prior server ETag absent. Record absence honestly; no If-Range is sent; empty equal validators are not entity-continuity proof.',
    'final_artifact': 'Only166873622 complete bytes with full SHA/readback and unchanged old inputs can be staged. New artifact remains pending normal full-APK v2/v3 signature, expected vendor signer, manifest version/package, SDK/ABI and fresh installed scope qualification.',
    'success_gate': ['durable process exit0 and complete untruncated output',
                     'exact prior source and failure gates passed', 'all38 requests complete without retries/refusal/signal',
                     'all owned curl children exited and pidfds closed', 'all prior held files closed with errors empty',
                     'whole original self descriptor identities restored', 'complete file full-hash readback',
                     'no unknown field interpreted as success'],
    'failure_action': 'Preserve original and new partial bytes/receipts; no automatic retry, cleanup of old versions or install.',
    'actual_HTTP_requests_by_preparation': 0, 'actual_remote_processes_by_preparation': 0,
    'Android_reads': 0, 'Main_lock_or_fds': 0, 'installs': 0, 'production_ready': False,
})
print(json.dumps({'source': source_ref, 'request': request_ref, 'diff': diff_ref,
                  'inheritance': inheritance_ref, 'plan': plan_ref}, indent=2))
