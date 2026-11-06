"""Pure local review of the exact actual prepared receipt and retained wire."""
import base64
import gzip
import hashlib
import json
from pathlib import Path
import re

ROOT = Path('/workspace/scratch/94990735b266')
EVIDENCE = ROOT / 'root-recovery-20261104-02/evidence'
SOURCE = ROOT / 'android-owner18-normal01-freeze-01'
OUT = ROOT / 'android-owner18-prepared-actual-review01'


def sha(body):
    return hashlib.sha256(body).hexdigest()


def pretty(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def main():
    checks = []
    def check(name, value):
        assert value, name
        checks.append(name)
    def read(relative, size, digest):
        body = (EVIDENCE / relative).read_bytes()
        check('exact ' + relative, len(body) == size and sha(body) == digest)
        return body, json.loads(body)
    raw, actual = read('owner18-prepared-read01/prepared.json', 55273,
        '0e8182f704c6c0f52f914c9d2f46392c646b20062baff3bfc46711dd75123fc7')
    wire_raw, wire = read('owner18-prepared-read01/stdout.log', 11967,
        'c82d9912b5a9678227a12d0368e9bc049e3177da6f6657fa07ef7c877f666796')
    compressed = base64.b64decode(wire['gzip_base64'], validate=True)
    check('full compressed wire hash', len(compressed) == wire['gzip_bytes'] and sha(compressed) == wire['gzip_sha256'])
    envelope_raw = gzip.decompress(compressed)
    check('full uncompressed envelope hash', len(envelope_raw) == wire['bytes'] == 61222 and
        sha(envelope_raw) == wire['sha256'] == '3a67aba6e05b9df45d975956cf76845aea6d9a34f38f42bce127788456c7eae6')
    envelope = json.loads(envelope_raw)
    check('collection complete and no errors or mutation', wire['collection_complete'] is True and
        envelope['collection_complete'] is True and envelope['errors'] == [] and
        envelope['mutations'] is False and envelope['qualification'] is False)
    check('single exact prepared original', set(envelope['files']) == {'prepared.json'} and
        envelope['files']['prepared.json']['content'].encode() == raw and
        envelope['files']['prepared.json']['sha256'] == sha(raw))
    for folder, job, count in [('owner18-normal-prepare01', '1a1ae54c8fd-fc05-5f12', 233),
                               ('owner18-prepared-read01', '1a1ae57800c-fc05-5f29', 11967)]:
        admission_path = EVIDENCE / folder / 'admission.tool-original.json'
        verification_path = EVIDENCE / folder / 'known-terminal-binary-read-verification.json'
        admission_raw = admission_path.read_bytes()
        verification_raw = verification_path.read_bytes()
        expected = {
            'owner18-normal-prepare01': (1018, 'f176b333a71e6a4b82adab8fc573588ded3a4052931b114c339eb44c1305c51d',
                597, '186651d59ff4d21a8ed4f271f934dab4a690d2ce3e2d487e5829be2558e904e4'),
            'owner18-prepared-read01': (1024, '716e348f79af6a0ac17e11eefb56a99080b8571be4316d21e37f6fd18d8c580b',
                605, '99fcb05694a672db2e08cd59f18b54bb2188a558a6cd780dffb8e5b29d76a876'),
        }[folder]
        check('retained admission and Root binary-verification pins ' + job,
            (len(admission_raw), sha(admission_raw), len(verification_raw), sha(verification_raw)) == expected)
        admission, verification = json.loads(admission_raw), json.loads(verification_raw)
        output = (EVIDENCE / folder / 'stdout.log').read_bytes()
        check('single original admission and durable bounded output ' + job,
            admission['job']['id'] == job and admission['reused'] is False and
            admission['job']['launch_state'] == 'launched' and admission['job']['launch_error'] is None and
            admission['local_record_pending'] is False and verification['job_id'] == job and
            verification['terminal_output_complete'] is True and verification['terminal_output_durable'] is True and
            verification['stderr_bytes'] == 0 and verification['bytes'] == len(output) == count and
            verification['sha256'] == sha(output))
    summary_raw, summary = read('owner18-normal-prepare01/stdout.log', 233,
        '1be888827e5e3938622aa4041354547b617a063dfe37143a76756d9d4d4301e0')
    check('original preparation summary binds report after close path', summary == {
        'success': True, 'result_path': '/opt/p4-owner18-normal-20261105-01-state/prepared.json',
        'bytes': len(raw), 'sha256': sha(raw), 'first_error': None, 'runtime_executed': False})
    manifest_raw = (SOURCE / 'manifest.json').read_bytes()
    check('frozen plan manifest', sha(manifest_raw) == '12db23737188644c67a8a60cff57ab77ed8f46a58512544e6129190c8355bd60')
    for row in json.loads(manifest_raw)['files']:
        body = (SOURCE / row['path']).read_bytes()
        assert len(body) == row['bytes'] and sha(body) == row['sha256'], row['path']
    checks.append('all 30 original frozen payload pins')
    plan = json.loads((SOURCE / 'plan.json').read_bytes())
    check('actual success with no runtime or namespace effects', actual['success'] is True and actual['errors'] == [] and
        actual['kind'] == 'owner18-normal-preparation01' and not actual['runtime_executed'] and
        not actual['namespace_or_network_changed'] and not actual['production_ready'])
    check('actual attempt and sorted plan hash', actual['attempt_nonce'] == plan['attempt_nonce'] and
        actual['plan_sha256'] == sha(pretty(plan)))
    canonical = (SOURCE / 'cell.json').read_bytes()
    check('exact canonical CellSpec', canonical == json.dumps(plan['spec'], ensure_ascii=False, separators=(',', ':')).encode() and
        sha(canonical) == actual['canonical_spec_sha256'] == plan['canonical_spec_sha256'])
    expected_sources = {f.name: {'bytes': len(f.read_bytes()), 'sha256': sha(f.read_bytes())}
                        for f in (SOURCE / 'source').glob('*.py')}
    check('all seven sources exactly prepared', len(expected_sources) == 7 and actual['source_files'] == expected_sources)
    check('exact five artifacts only', set(actual['copied_artifacts']) == set(plan['artifacts']) and len(plan['artifacts']) == 5)
    for role, row in actual['copied_artifacts'].items():
        expected = plan['artifacts'][role]
        check('actual copied ' + role, row['path'] == plan['package'] + '/' + expected['destination'] and
            row['bytes'] == expected['bytes'] and row['sha256'] == expected['sha256'] and
            row['identity']['device'] == actual['package_identity']['device'] and row['identity']['inode'] > 0)
    base = actual['base_before']
    check('base86 entire original identities unchanged', base == actual['base_after'] and len(base) == 86 and
        len({row['relative'] for row in base}) == 86)
    expected_base = {row['relative']: {key: row[key] for key in ('bytes', 'sha256')} for row in plan['base']['records']}
    check('base86 each bytes and SHA equals plan', {row['relative']: {key: row[key] for key in ('bytes', 'sha256')} for row in base} == expected_base)
    main = actual['main_before']
    check('all three original Main gates equal', main == actual['main_after'] == actual['main_final'])
    check('Main unit framework five limits exact original12288', main['framework_sha256'] == plan['main']['framework_sha256'] and
        main['daemon'] == plan['main']['daemon'] and main['resources'] == plan['main']['resources'] and
        main['resources']['pids.max'] == '12288' and main['held_cgroup_identity'] == [30, 26651611] and
        main['original_processes_alive_and_unchanged'] is True and main['installed_contract_unchanged'] is True)
    check('all eight fixed tools', set(actual['tools']) == set(plan['tools_fixed_paths']) == set(plan['tools_sha256']))
    for path, row in actual['tools'].items():
        check('actual fixed tool ' + path, row['path'] == path and row['sha256'] == plan['tools_sha256'][path] and
            row['bytes'] > 0 and row['identity']['inode'] > 0 and row['mode'] & 0o111 != 0 and row['mode'] & 0o022 == 0)
    check('actual presenter same paired artifact', actual['presenter']['path'] == plan['presenter']['path'] and
        actual['presenter']['sha256'] == plan['presenter']['sha256'])
    check('two fresh ext4 images original shape', len(actual['data_images']) == len(plan['data_images']) == 2)
    for row, expected in zip(actual['data_images'], plan['data_images']):
        check('actual fresh image ' + row['name'], row['name'] == expected['name'] and row['bytes'] == expected['bytes'] and
            row['returncode'] == 0 and row['fresh_sparse_created'] is True and row['existing_userdata_copied'] is False and
            row['identity']['device'] == actual['state_identity']['device'] and row['identity']['inode'] > 0 and
            len(row['stdout'].encode()) + len(row['stderr'].encode()) <= 65536)
    ids = actual['id_availability']
    check('actual proposed IDs available without reservation', ids['available_at_observation'] and
        ids['host_uid'] == plan['spec']['host_uid'] and ids['subordinate_range'] == plan['spec']['subordinate_uids'] == plan['spec']['subordinate_gids'] and
        ids['reservation_created_in_passwd_or_subid_tables'] is False and set(ids['tables']) == {'/etc/subuid', '/etc/subgid'})
    resources = actual['resources_before']; full = re.search(r'^full avg10=([0-9.]+)', resources['memory_pressure'], re.M)
    check('actual fresh memory disk PSI admission', resources['MemAvailable_bytes'] >= plan['mem_available_min_bytes'] and
        resources['disk_available_bytes'] >= plan['disk_available_min_bytes'] and full and float(full[1]) <= plan['host_memory_full_avg10_max'])
    check('actual state root same as independent protected reader', actual['state_identity'] == {
        'device': envelope['root_identity'][0], 'inode': envelope['root_identity'][1]})
    report = {'schema': 1, 'result': 'ACTUAL_PREPARATION_PASS_RUNTIME_NOT_EXECUTED_BY_REVIEW',
        'actual_prepared': {'bytes': len(raw), 'sha256': sha(raw)}, 'original_summary_sha256': sha(summary_raw),
        'collector_stdout_sha256': sha(wire_raw), 'checks': checks, 'check_count': len(checks),
        'source_files': 7, 'artifacts': actual['copied_artifacts'], 'base_records': 86, 'fixed_tools': 8,
        'data_images': [{key: row[key] for key in ('name', 'bytes', 'identity', 'returncode', 'fresh_sparse_created', 'existing_userdata_copied')} for row in actual['data_images']],
        'Main_three_exact_maps': main, 'actual_id_availability': ids, 'actual_resources_before': resources,
        'canonical_spec_sha256': sha(canonical), 'actual_sorted_plan_sha256': actual['plan_sha256'],
        'held_prepared_file_identity': envelope['files']['prepared.json']['identity'],
        'limits': ['Original preparation exit0 summary is emitted after its fixed FD closes; no independent FD-table census was performed.',
                   'Authoritative exit0 was reported by Root; these two local directories retain exact admission plus Root terminal-output verification, not a standalone original process_status record. No independent raw status claim is made here.',
                   'The two mkfs returncodes are from frozen subprocess.run direct-child joins; no independent child scan or ext4 header read.',
                   'The original MainFence revalidates its seven process identities and artifacts; this report consumes its complete returned maps, not a new Main scan.',
                   'UID61288/subid availability is a point observation, not a reservation or assertion that init runs with that UID.',
                   'No runtime, LMKD execution repair, HWS health, complete log stream or App qualification follows from preparation.'],
        'runtime_executed_by_review': False, 'mutable_private_logdr_WIP_included': False,
        'exact_frozen_crash_observer_included': True, 'actual_peer_protocol_qualified': False, 'whole_App_qualified': False}
    files = {'report.json': pretty(report), 'check.py': Path(__file__).read_bytes()}
    OUT.mkdir()
    for name, body in files.items():
        with (OUT / name).open('xb') as stream: stream.write(body)
    (OUT / 'manifest.json').write_bytes(pretty({'schema': 1, 'files': [{'path': n, 'bytes': len(b), 'sha256': sha(b)} for n, b in files.items()]}))
    print(json.dumps({'checks': len(checks), 'report_bytes': len(files['report.json']), 'report_sha256': sha(files['report.json'])}))


if __name__ == '__main__':
    main()
