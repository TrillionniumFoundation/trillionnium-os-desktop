"""One fixed admitted namespace role; no arbitrary command or automatic retry."""
import hashlib, json, pathlib, sys
C = pathlib.Path(__file__).parent
assert len(sys.argv) == 5
accepted, admission_sha, role, role_manifest_sha = sys.argv[1:]
raw = (C / 'SOURCE-MANIFEST.json').read_bytes(); assert hashlib.sha256(raw).hexdigest() == accepted
manifest = json.loads(raw)
for name in ('common.py', 'storage_support.py', 'rotation_support.py'):
    body = (C / name).read_bytes(); assert hashlib.sha256(body).hexdigest() == manifest['files'][name]['sha256']
    exec(compile(body, str(C / name), 'exec'))
contract = json.loads((C / 'contract.json').read_bytes())
admission_ref, admission = storage_admission(C, accepted, admission_sha, contract)
need(str(C) == contract['desktop_source'] and os.getresuid() == os.getresgid() == (0, 0, 0), 'root fixed role dispatch')
need(role in contract['role_units'], 'one finite production build role')
boot_is(contract['hosts']['desktop']['boot']); _, sources = sealed_sources(C, accepted)
Q = P(contract['desktop_root'])
ready_ref, ready = root_record(Q / 'OWNER-READY.json')
need(ready['nonce'] == contract['nonce'] and ready['source_manifest_sha256'] == accepted and
     ready['admission_sha256'] == admission_sha and not (Q / 'STOPPING.json').exists(), 'original live storage generation')
role_root = P(contract['import_source_dir'] if role == 'source_import' else contract['full_source_dir'])
role_ref, selected = root_record(role_root / 'ROLE-SOURCE-MANIFEST.json')
need(role_ref['sha256'] == role_manifest_sha and selected['schema'] == 'p4-production651-role-source-v1' and
     selected['storage_source_manifest_sha256'] == accepted and selected['storage_admission_sha256'] == admission_sha and
     role in selected['roles'], 'separate reviewed actual role source')
unit = contract['role_units'][role]
directory = Q / 'role-controls'
if not directory.exists(): directory.mkdir(mode=0o700)
run = directory / role
intent_path = Q / 'actor-intents' / (role + '.json')
argv = ['/usr/bin/python3', '-I', '-B', str(C / 'namespace_entry.py'), accepted, admission_sha, role, role_manifest_sha]
if intent_path.exists():
    _, original = root_record(intent_path); validate_role_intent(contract, accepted, admission_sha, role, original)
    need(original['role_manifest_sha256'] == role_manifest_sha, 'same accepted role source on uncertain ACK')
    observation = run / ('reconcile-' + str(time.time_ns())); observation.mkdir(mode=0o700)
    commands = Commands(observation); actor = OwnedUnit.recover(commands, run, unit)
    need(actor.argv == argv, 'same already dispatched role argv')
    print(json.dumps({'reused_original_intent': True, 'new_starts': 0, 'actual': actor.ref}, sort_keys=True))
    if actor.held is not None: actor.held.close()
    raise SystemExit(0)
need(not run.exists(), 'new role control generation'); run.mkdir(mode=0o700)
commands = Commands(run)
owner = HeldProcess(ready['native']['pid'])
try:
    need(owner.start == ready['native']['start_ticks'] and owner.live(), 'held original namespace owner')
    state = show(commands, contract['controller_unit'])
    need(state['InvocationID'] == ready['native']['InvocationID'] and state['MainPID'] == str(owner.pid), 'actual owner invocation')
    description = role_description(contract, role)
    intent = {'schema': 'p4-production651-storage-role-intent-v1', 'role': role, 'unit': unit,
        'description': description, 'nonce': contract['nonce'], 'source_manifest_sha256': accepted,
        'admission_sha256': admission_sha, 'role_manifest_sha256': role_manifest_sha,
        'argv': argv, 'boot': contract['hosts']['desktop']['boot'], 'created_monotonic_ns': time.monotonic_ns(),
        'owner_ready': ready_ref, 'role_manifest': role_ref, 'H_job_id': None}
    save(intent_path, intent, 0o444)
    if role == 'source_import':
        props = ['MemoryMax=2147483648', 'MemoryHigh=1610612736', 'CPUAffinity=6 7', 'TasksMax=128',
                 'RuntimeMaxSec=14400', 'NoNewPrivileges=yes']
    elif role.endswith('_outer'):
        props = ['MemoryMax=2147483648', 'CPUAffinity=8 9', 'TasksMax=128',
                 'RuntimeMaxSec=27600', 'NoNewPrivileges=no']
    else:
        props = ['MemoryMax=12884901888', 'MemoryHigh=10737418240', 'CPUAffinity=8 9', 'TasksMax=512',
                 'RuntimeMaxSec=22800', 'NoNewPrivileges=no']
    props += ['AllowedCPUs=' + ('6 7' if role == 'source_import' else '8 9'), 'MemorySwapMax=0', 'CPUQuota=200%', 'Nice=10', 'OOMPolicy=stop', 'Restart=no',
              'TimeoutStopSec=1200', 'LimitFSIZE=infinity', 'WorkingDirectory=' + str(C)]
    actor = OwnedUnit(commands, unit, description, 0, argv, run, props)
    actor.launch()
    public = Q / 'role-receipts'
    if not public.exists(): public.mkdir(mode=0o755)
    ref = save(public / (role + '.json'), {'schema': 'p4-production651-role-dispatch-v1',
        'intent': intent, 'actual': actor.ref, 'source_manifest_sha256': accepted,
        'admission_sha256': admission_sha, 'role_manifest': role_ref, 'H_job_id': None}, 0o444)
    sources_unchanged(sources); pin(admission_ref['path'], admission_ref)
    print(json.dumps({'dispatch': ref, 'actual': actor.ref, 'build_success_not_inferred': True}, sort_keys=True))
    if actor.held is not None: actor.held.close()
finally: owner.close()
