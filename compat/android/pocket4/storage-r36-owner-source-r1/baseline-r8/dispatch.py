"""Dispatch one fixed storage actor; uncertain ACK reconciles the same original unit."""
import datetime, hashlib, json, pathlib, sys
C = pathlib.Path(__file__).parent
assert len(sys.argv) >= 4
role, accepted, admission_sha = sys.argv[1:4]
assert role in ('server', 'controller', 'finalize')
raw = (C / 'SOURCE-MANIFEST.json').read_bytes(); assert hashlib.sha256(raw).hexdigest() == accepted
manifest = json.loads(raw)
for name in ('common.py', 'storage_support.py', 'rotation_support.py'):
    body = (C / name).read_bytes(); assert hashlib.sha256(body).hexdigest() == manifest['files'][name]['sha256']
    exec(compile(body, str(C / name), 'exec'))
contract = json.loads((C / 'contract.json').read_bytes())
admission_ref, admission = storage_admission(C, accepted, admission_sha, contract)
need(os.getresuid() == os.getresgid() == (0, 0, 0), 'root fixed storage dispatch')
host = 'desktop' if role == 'controller' else 'pocket4'
need(str(C) == contract['desktop_source' if host == 'desktop' else 'p4_source'], 'fixed source host')
boot_is(contract['hosts'][host]['boot']); check_tools(contract, host); _, sources = sealed_sources(C, accepted)
extra = sys.argv[4:]
need((role == 'finalize' and len(extra) == 2 and all(re.fullmatch('[a-f0-9]{64}', x) for x in extra)) or
     (role != 'finalize' and not extra), 'only exact finalization result references may be added')
script = {'server': 'p4_server.py', 'controller': 'desktop_owner.py', 'finalize': 'p4_finalize.py'}[role]
argv = ['/usr/bin/python3', '-I', '-B', str(C / script), accepted, admission_sha] + extra
directory = C / (role + '-dispatch'); unit = contract[role + '_unit']
if directory.exists():
    need(directory.resolve() == directory and directory.lstat().st_uid == 0, 'original fixed dispatch directory')
    observation = directory / ('reconcile-' + str(time.time_ns())); observation.mkdir(mode=0o700)
    commands = Commands(observation); actor = OwnedUnit.recover(commands, directory, unit)
    need(actor.argv == argv, 'same original storage argv and final input hashes')
    print(json.dumps({'reused_intent': True, 'new_starts': 0, 'actual': actor.ref, 'H_job_id': None}, sort_keys=True))
    if actor.held is not None: actor.held.close()
    raise SystemExit(0)
if role != 'finalize':
    need(datetime.datetime.fromisoformat(admission['lease_until_utc']) > datetime.datetime.now(datetime.timezone.utc),
         'unexpired storage admission before initial export/mount dispatch')
    if host == 'pocket4': pin(admission['canonical']['path'], admission['canonical'])
    if host == 'desktop':
        need(mem_available() >= contract['desktop_fresh_memory_minimum'] and
             free_space(P(contract['desktop_root']).parent) >= contract['desktop_local_disk_minimum'], 'fresh composite desktop reserve')
    else:
        need(mem_available() >= contract['p4_fresh_memory_minimum'] and
             free_space(P(contract['p4_root']).parent) >= contract['p4_fresh_disk_minimum'], 'fresh Pocket4 reserve')
directory.mkdir(mode=0o700); commands = Commands(directory)
save(directory / 'DISPATCH-HOST.json', host_mac_state())
uid = 0 if role == 'controller' else 1000
runtime = 14400 if role == 'finalize' else contract['storage_runtime_max_seconds']
props = ['MemoryMax=536870912', 'MemoryHigh=402653184', 'MemorySwapMax=0', 'CPUQuota=200%',
         'CPUAffinity=' + ('6 7' if uid == 0 else '2 3'),
         'AllowedCPUs=' + ('6 7' if uid == 0 else '2 3'), 'TasksMax=' + ('128' if uid == 0 else '64'),
         'Nice=15', 'NoNewPrivileges=yes', 'OOMPolicy=stop', 'Restart=no',
         'RuntimeMaxSec=' + str(runtime), 'TimeoutStopSec=1200', 'WorkingDirectory=' + str(C)]
if role == 'controller': props.append('PrivateMounts=yes')
else: props.append('RestrictAddressFamilies=AF_UNIX')
actor = OwnedUnit(commands, unit, contract[role + '_description'], uid, argv, directory, props)
actor.launch(); sources_unchanged(sources); pin(admission_ref['path'], admission_ref)
print(json.dumps({'actual': actor.ref, 'H_job_id': None, 'functional_success_not_inferred': True}, sort_keys=True))
if actor.held is not None: actor.held.close()
