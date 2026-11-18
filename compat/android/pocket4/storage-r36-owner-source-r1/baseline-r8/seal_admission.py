"""Seal exact reviewed rotation inputs on either host, or the Pocket4 admission on desktop."""
import hashlib, json, pathlib, sys
C = pathlib.Path(__file__).parent
assert len(sys.argv) == 4
accepted, mode, expected_sha = sys.argv[1:]
raw = (C / 'SOURCE-MANIFEST.json').read_bytes(); assert hashlib.sha256(raw).hexdigest() == accepted
manifest = json.loads(raw)
for name in ('common.py', 'storage_support.py'):
    source = (C / name).read_bytes()
    assert len(source) == manifest['files'][name]['bytes'] and hashlib.sha256(source).hexdigest() == manifest['files'][name]['sha256']
    exec(compile(source, str(C / name), 'exec'))
contract = json.loads((C / 'contract.json').read_bytes())
hosts = [host for host, key in (('pocket4', 'p4_source'), ('desktop', 'desktop_source')) if str(C) == contract[key]]
need(len(hosts) == 1 and os.getresuid() == os.getresgid() == (0, 0, 0), 'one fixed root source directory and host')
host = hosts[0]
need(mode in ('rotation', 'admission') and (mode == 'rotation' or host == 'desktop'),
     'fixed rotation seal on either host, admission copy only on desktop')
boot_is(contract['hosts'][host]['boot']); _, sources = sealed_sources(C, accepted)
if mode == 'rotation':
    incoming = P(contract['incoming_rotation_paths'][host])
    target = P(contract['rotation_inputs_paths'][host])
    need(target == C / 'ROTATION-INPUTS.json', 'fixed new generation rotation input seal')
else:
    incoming = P(contract['incoming_admission_path'])
    target = C / 'ADMISSION.json'
ref, body = pin(incoming)
need(ref['sha256'] == expected_sha and ref['identity'][3:6] == [1000, 1000, 1] and
     stat.S_IMODE(ref['identity'][2]) == 0o600, 'exact complete ordinary incoming body')
value = json.loads(body)
if mode == 'rotation':
    source = (C / 'rotation_support.py').read_bytes()
    need(len(source) == manifest['files']['rotation_support.py']['bytes'] and
         hashlib.sha256(source).hexdigest() == manifest['files']['rotation_support.py']['sha256'],
         'exact reviewed rotation validator')
    exec(compile(source, str(C / 'rotation_support.py'), 'exec'))
    validate_rotation_data(contract, host, value)
else:
    need(value['schema'] == 'p4-nbd-final-current-admission-v1' and
         value['stage'] == 'production651_failed_epoch_storage_only' and value['nonce'] == contract['nonce'] and
         value['source_manifest_sha256'] == accepted and value['pocket4_boot'] == contract['hosts']['pocket4']['boot'] and
         value['allocation_source_manifest_sha256'] == contract['allocation_source_manifest_sha256'],
         'exact Pocket4 storage admission bytes and source cohort')
    validate_failed_storage_admission(value, contract)
sources_unchanged(sources); pin(incoming, ref)
if os.path.lexists(target):
    old, old_body = pin(target)
    need(old_body == body and old['identity'][3:6] == [0, 0, 1] and stat.S_IMODE(old['identity'][2]) == 0o444,
         'same original complete root seal on uncertain acknowledgement')
    result = {('existing_original_rotation_inputs' if mode == 'rotation' else 'existing_original_admission'): old,
              'storage_started': False}
else:
    result = save(target, body, 0o444)
sources_unchanged(sources); pin(incoming, ref)
print(json.dumps(result, sort_keys=True))
