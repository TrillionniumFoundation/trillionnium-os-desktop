#!/usr/bin/env python3
"""Read-only evidence verification; optional explicit restore into a new directory.

Does not invoke Git, Cargo, make, QEMU, or any captured controller/command.
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile

BASE = Path(__file__).resolve().parent

def require(ok, message):
    if not ok:
        raise ValueError(message)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def rel(name):
    p = PurePosixPath(name)
    require(bool(name) and not p.is_absolute() and '..' not in p.parts and '.' not in p.parts, 'unsafe path: '+name)
    require(str(p) == name and '\\' not in name, 'noncanonical path: '+name)
    return p

def file_bytes(name):
    p = BASE.joinpath(*rel(name).parts)
    require(p.is_file() and not p.is_symlink(), 'missing regular file: '+name)
    return p.read_bytes()

def load(name):
    return json.loads(file_bytes(name))

def check_payload(data, record, label):
    require(len(data) == record['bytes'], label+' size mismatch')
    require(sha(data) == record['sha256'], label+' SHA256 mismatch')

def archive(name, manifest, source=False):
    raw = file_bytes(name)
    check_payload(raw, manifest, name)
    expected = {x['member']: x for x in manifest['members']}
    require(len(expected) == len(manifest['members']), name+' duplicate manifest member')
    result = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as tf:
        for member in tf.getmembers():
            rel(member.name)
            require(member.isfile() and member.name not in result, name+' nonregular or duplicate member')
            require(member.name in expected, name+' unexpected member: '+member.name)
            record = expected[member.name]
            require(member.mode == record['archive_mode' if source else 'mode'], name+' mode mismatch')
            payload = tf.extractfile(member).read()
            check_payload(payload, record, member.name)
            if source:
                blob = hashlib.sha1(b'blob '+str(len(payload)).encode()+b'\0'+payload).hexdigest()
                require(blob == record['git_blob'], member.name+' Git blob mismatch')
            result[member.name] = payload
    require(set(result) == set(expected), name+' missing member')
    return result

def verify(restore=None):
    expected = {}
    for line in file_bytes('SHA256SUMS').decode().splitlines():
        digest, name = line.split('  ', 1)
        rel(name)
        require(re.fullmatch('[0-9a-f]{64}', digest) is not None and name not in expected, 'invalid checksum record')
        expected[name] = digest
    actual = {str(p.relative_to(BASE)) for p in BASE.rglob('*') if p.is_file() and p.name != 'SHA256SUMS'}
    require(set(expected) == actual, 'SHA256SUMS coverage mismatch')
    for name, digest in expected.items():
        require(sha(file_bytes(name)) == digest, 'checksum mismatch: '+name)

    raw_meta = load('raw-members.json')
    raw = archive('raw.tar.gz', raw_meta)
    require(len(raw) == 37, 'raw scope count changed')
    for name, payload in raw.items():
        require(file_bytes('readable/'+name) == payload, 'readable/raw mismatch: '+name)
    artifacts = load('artifacts/manifest.json')
    originals = {}
    for artifact in artifacts['artifacts']:
        pieces = []
        for chunk in artifact['chunks']:
            data = file_bytes(chunk['path'])
            check_payload(data, chunk, chunk['path'])
            require(len(data) <= 2*1024*1024, 'oversize binary chunk')
            pieces.append(data)
        zipped = b''.join(pieces)
        require(len(zipped) == artifact['gzip_bytes'] and sha(zipped) == artifact['gzip_sha256'], 'reassembled gzip mismatch')
        data = gzip.decompress(zipped)
        require(len(data) == artifact['original_bytes'] and sha(data) == artifact['original_sha256'], 'original binary input mismatch')
        originals[artifact['original_sha256']] = data
    require(len(originals) == 3, 'deduplicated binary input count changed')
    logical = {}
    for name, record in artifacts['original_current_cloud_paths'].items():
        rel(name)
        data = originals[record['artifact']]
        check_payload(data, record, name)
        logical['current-cloud/'+name] = data
    require(len(logical) == 5 and not (set(raw)&set(logical)), 'logical binary path scope changed')
    all_inputs = dict(raw, **logical)
    capture = load('capture.json')
    require(len(capture['files']) == 42, 'capture scope changed')
    captured_names = set()
    for record in capture['files']:
        name = 'current-cloud/'+record['path'] if 'path' in record else 'controllers/'+record['controller']
        require(record['read_stable'] is True, 'unstable capture: '+name)
        check_payload(all_inputs[name], record, name)
        captured_names.add(name)
    require(captured_names == set(all_inputs), 'capture coverage mismatch')
    require(capture['original_empty_directories'] == ['boot-data-retry'], 'retry empty-directory scope changed')

    source_meta = load('source/members.json')
    sources = archive('source/controls.tar.gz', source_meta, source=True)
    require(len(sources) == 23, 'selected source scope count changed')
    binding = load('source-binding.json')
    for commit, record in binding['commits'].items():
        data = record['commit_object'].encode()
        require(hashlib.sha1(b'commit '+str(len(data)).encode()+b'\0'+data).hexdigest() == commit, 'Git commit object mismatch')
        require(record['commit_object'].splitlines()[0] == 'tree '+record['tree'], 'commit/tree binding mismatch')
    producer = binding['producer_local_commit']
    published = binding['published_tree_equivalent_commit']
    retry = binding['retry_published_commit']
    require(binding['commits'][producer]['tree'] == binding['commits'][published]['tree'] == '8c1902eb85f94a9285a0b34689c8c696fd716c17', 'producer/published full tree mismatch')
    require({r['kernel_tree'] for r in binding['commits'].values()} == {'6b3cab110aa6d30d5b89f99c4389c9c3e01022da'}, 'kernel tree mismatch')

    def current(name):
        return all_inputs['current-cloud/'+name]
    commands = json.loads(current('commands.json'))
    retry_commands = json.loads(current('retry-commands.json'))
    require([(r['name'],r['returncode']) for r in commands] == [('worktree',0),('source-verification',0),('full-kernel-build',0),('full-kernel-boot',2)], 'baseline command outcomes changed')
    require([(r['name'],r['returncode']) for r in retry_commands] == [('initial-status',0),('kernel-tree-binding',0),('checkout',0),('source-verification',0),('boot',1)], 'retry command outcomes changed')
    for command in commands+retry_commands:
        name = 'current-cloud/'+command['log'].split('/current-cloud/',1)[1]
        require(sha(all_inputs[name]) == command['log_sha256'] and len(all_inputs[name]) == command['log_size'], 'controller/log binding mismatch')
    require(len(re.findall(rb'^\s*Compiling\s',current('build/kernel.log'),re.M)) == 279, 'build compile-line scope changed')
    require(len(re.findall(rb'^\s*Compiling\s',current('boot/run_kernel.log'),re.M)) == 0, 'cached boot compile-line scope changed')
    qemu = json.loads(current('boot/qemu.json'))
    require(qemu['raw_exit_code'] == 124 and qemu['timed_out'] is True and qemu['recorder_exit_code'] == 124, 'QEMU timeout status changed')
    require('-L' not in qemu['argv'], 'first QEMU unexpectedly has explicit data selection')
    serial = current('boot/serial.log')
    require(len(serial) == 217 and sha(serial) == qemu['serial_sha256'] and b'No bootable device.' in serial, 'failure serial changed')
    for key, snapshot in qemu['artifacts'].items():
        name = 'current-cloud/'+snapshot['path'].split('/current-cloud/',1)[1]
        require(len(all_inputs[name]) == snapshot['size'] and sha(all_inputs[name]) == snapshot['sha256'], 'QEMU input snapshot mismatch: '+key)
    for rom in [b"Could not open option rom 'kvmvapic.bin'",b"Could not open option rom 'multiboot_dma.bin'"]:
        require(rom in current('boot/run_kernel.log'), 'missing ROM diagnostic absent')
    require(b'kernel/OSDK.toml already exists; refusing to replace it' in current('retry-boot.log'), 'retry preflight diagnostic absent')
    require(not any(k.startswith('current-cloud/boot-data-retry/') for k in all_inputs), 'unexpected retry VM evidence')
    for phase, outcome in [('build','owned_removed'),('boot','foreign_restored')]:
        cleanup = json.loads(current(phase+'/manifest-cleanup.json'))
        require(cleanup['outcome'] == outcome and cleanup['passed'] is True, 'cleanup receipt changed')
    foreign = json.loads(current('retained-foreign-manifest.json'))
    require(len(current('retained-foreign-manifest.toml')) == foreign['size'] and sha(current('retained-foreign-manifest.toml')) == foreign['sha256'], 'retained foreign manifest mismatch')
    report = load('report.json')
    require(report['kernel_boot_passed'] is False and report['retry']['qemu_raw_exit_code'] is None and report['retry']['new_vm_launched'] is False, 'report overstates boot/retry result')

    restored = None
    if restore is not None:
        destination = Path(restore).absolute()
        require(destination != BASE and BASE not in destination.parents, 'restore destination must be outside evidence phase')
        destination.mkdir(parents=False, exist_ok=False)
        for directory in capture['original_current_cloud_directories']:
            destination.joinpath('current-cloud',*rel(directory).parts).mkdir(parents=True,exist_ok=True)
        for name, data in all_inputs.items():
            target = destination.joinpath(*rel(name).parts)
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as stream:
                stream.write(data)
            require(target.read_bytes() == data, 'restore readback mismatch: '+name)
        restored = str(destination)
    return {'passed':True,'sha256sum_entries':len(expected),'raw_archive_regular_members':len(raw),'selected_source_regular_members':len(sources),'original_current_cloud_files':40,'controllers':2,'deduplicated_binary_inputs':len(originals),'logical_binary_paths':len(logical),'kernel_boot_passed':False,'retry_new_vm_launched':False,'restore_directory':restored,'scope':'Read-only archive, SHA, source identity and recorded failure semantics; no build, host test suite or VM executed.'}

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restore',metavar='NEW_DIRECTORY',help='explicitly reconstruct the 40 original evidence files plus two controllers outside this phase; never execute them')
    args=parser.parse_args()
    try:
        print(json.dumps(verify(args.restore),indent=2))
    except (ValueError,KeyError,OSError,tarfile.TarError,EOFError) as error:
        print('verification failed: '+str(error),file=sys.stderr)
        sys.exit(1)
