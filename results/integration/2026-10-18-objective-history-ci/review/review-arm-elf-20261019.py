#!/usr/bin/env python3
"""Independently inspect restored ARM artifact bytes, without extracting/executing."""
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import struct
import tarfile
import zipfile


class CountedReader:
    def __init__(self, stream):
        self.stream, self.count, self.sha = stream, 0, hashlib.sha256()

    def read(self, size=-1):
        block = self.stream.read(size)
        self.count += len(block)
        self.sha.update(block)
        return block

    def tell(self):
        return self.count


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe(name):
    p = PurePosixPath(name)
    return not p.is_absolute() and len(p.parts) == 1 and p.parts[0] not in ('', '.', '..') and '\\' not in name


root = Path('/workspace/scratch/499c7902de8e/r9-evidence/ci')
started = datetime.now(timezone.utc).isoformat()
with zipfile.ZipFile(root/'r9-history-arm-evidence-39115155092.zip') as z:
    report_bytes = z.read('work/report.json')
    builds_bytes = z.read('identity/builds.json')
report = json.loads(report_bytes)
archive_name = 'hepta-objective-history-aarch64-linux.tar.gz'
checks = []
with zipfile.ZipFile(root/'r9-history-arm-elf-39115155092.zip') as z:
    infos = z.infolist()
    assert len(infos) == 4 and {i.filename for i in infos} == {archive_name, 'binary-manifest.json', 'SHA256SUMS', 'archive.sha256'}
    for info in infos:
        assert safe(info.filename) and not info.is_dir() and not (info.flag_bits & 1)
        assert stat.S_ISREG(info.external_attr >> 16) and not stat.S_ISLNK(info.external_attr >> 16)
    manifest_bytes, sums_bytes = z.read('binary-manifest.json'), z.read('SHA256SUMS')
    manifest = json.loads(manifest_bytes)
    assert z.read('archive.sha256').decode().split() == ['d9d2593d5dc92790a11eeb538d3962466b52936d332f51b3f8b5c2d9c39bc846', archive_name]
    assert sha(report_bytes) == manifest['report_sha256'] == '703545addc305db4fb055a801b4b9bfa7b4e5cb088fb8179b92f9b106aef9ca3'
    assert sha(builds_bytes) == manifest['build_receipt_sha256'] == '732a1f90741f6a3e39bd93e6faf69d0561530d852bb488b8ba852984ca35ddba'
    assert manifest['desktop_commit'] == '46dcb2d691827f7aa3ad7903dae09d39fd338126'
    assert manifest['desktop_tree'] == '8d5de807c41090e3d987764daec9c235ebd022a1'
    assert manifest['upstream']['commit'] == '2be5fc052ae7b2e9fb08c68a3ae7e5a218ad37d5'
    assert manifest['upstream']['tree'] == 'f4ef891d43baf90d6eebd29921a5ed03222ef3ab'
    assert report['status'] == 'passed' and report['runtime_executed'] is True
    assert manifest['compiled_source_binding'] == report['compiled_source_binding']
    assert manifest['upstream'] == report['upstream']
    assert [r for r in report['runtime_records'] if r.get('event') == 'acceptance_pass'] == [manifest['acceptance']]
    by_name = {v['filename']:(k,v) for k,v in manifest['binaries'].items()}
    assert len(by_name) == 5 and set(manifest['binaries']) == {'agentd', 'probe', 'observer', 'submitter', 'history'}
    sum_lines = [line.split() for line in sums_bytes.decode().splitlines()]
    assert len(sum_lines) == 5 and len({line[1] for line in sum_lines}) == 5
    assert {n:h for h,n in sum_lines} == {n:v['sha256'] for n,(_,v) in by_name.items()}
    small = {'binary-manifest.json':manifest_bytes, 'SHA256SUMS':sums_bytes, 'report.json':report_bytes}
    seen = set()
    with z.open(archive_name) as zipped:
        compressed = CountedReader(zipped)
        with gzip.GzipFile(fileobj=compressed, mode='rb') as gz:
            with tarfile.open(fileobj=gz, mode='r|') as tar:
                for entry in tar:
                    assert safe(entry.name) and entry.name in set(by_name)|set(small) and entry.name not in seen
                    assert entry.isreg() and not entry.issparse()
                    seen.add(entry.name)
                    f = tar.extractfile(entry)
                    assert f is not None
                    if entry.name in small:
                        assert entry.size == len(small[entry.name]) and f.read() == small[entry.name]
                        checks.append({'name':entry.name, 'kind':'identical_metadata', 'bytes':entry.size, 'sha256':sha(small[entry.name])})
                        continue
                    role, expected = by_name[entry.name]
                    assert entry.size == expected['bytes']
                    h, n, header = hashlib.sha256(), 0, b''
                    while block := f.read(1024*1024):
                        if not header:
                            header = block[:64]
                        h.update(block)
                        n += len(block)
                    assert n == expected['bytes'] and h.hexdigest() == expected['sha256']
                    assert header[:7] == b'\x7fELF\x02\x01\x01'
                    elf_type, machine, version = struct.unpack_from('<HHI',header,16)
                    assert elf_type in (2,3) and machine == 183 and version == 1
                    assert struct.unpack_from('<H',header,52)[0] == 64
                    assert report['binaries'][role]['bytes'] == n and report['binaries'][role]['sha256'] == h.hexdigest()
                    assert PurePosixPath(report['binaries'][role]['path']).name == entry.name
                    checks.append({'name':entry.name, 'role':role, 'kind':'actual_elf_bytes', 'bytes':n, 'sha256':h.hexdigest(), 'elf_class_bits':64, 'endianness':'little', 'e_machine':machine, 'architecture':'AArch64', 'elf_type':elf_type})
            while gz.read(1024*1024):
                pass
        while compressed.read(1024*1024):
            pass
        assert compressed.count == z.getinfo(archive_name).file_size == 91399979
        assert compressed.sha.hexdigest() == 'd9d2593d5dc92790a11eeb538d3962466b52936d332f51b3f8b5c2d9c39bc846'
    assert seen == set(by_name)|set(small)
    (root/'arm-binary-manifest.json').write_bytes(manifest_bytes)
result = {
    'schema':'r10.restored-arm-elf-byte-review.v1',
    'status':'passed_actual_restored_arm_elf_byte_review',
    'started_at_utc':started,'ended_at_utc':datetime.now(timezone.utc).isoformat(),
    'source_run_id':39115155092,'attempt':1,'source_job_id':117655596136,
    'artifact':{'id':12135470347,'bytes':90606774,'sha256':'1a145400d57620ecbcdcf533134ce4f2c45a47d58c5e95735c4192adb993bb63','digest_verified_by':'arm-elf-recovery-acquisition-20261019.json'},
    'archive':{'name':archive_name,'bytes':compressed.count,'sha256':compressed.sha.hexdigest()},
    'desktop_commit':manifest['desktop_commit'],'desktop_tree':manifest['desktop_tree'],'upstream':manifest['upstream'],
    'report_sha256':sha(report_bytes),'build_receipt_sha256':sha(builds_bytes),
    'outer_members':4,'inner_members':8,'all_zip_crc_and_gzip_footer_validated':True,
    'all_members_unique_regular_safe_unencrypted':True,
    'checks':checks,'actual_elf_count':5,'actual_elf_bytes':sum(v['bytes'] for v in checks if v['kind']=='actual_elf_bytes'),
    'source_acceptance_report_manifest_and_sums_matched':True,
    'new_build_or_runtime_executed':False,'binary_extraction_or_execution':False,
    'recovery_note':'The earlier 2026-10-18 temporary byte-review file was lost. This is a new independently executed data review of the same hash-verified original artifact after the workspace reset, with its own timestamp and identity; it does not recreate the old receipt SHA.',
    'scope':'Five actual ARM64 Linux ELF bytes tied to the original isolated Objective history qualification, not new Asterinas/device/production/G1/G2 execution.'
}
output = root/'arm-elf-artifact-review-20261019.json'
output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'path':str(output),'bytes':output.stat().st_size,'sha256':sha(output.read_bytes()),'status':result['status'],'actual_elf_bytes':result['actual_elf_bytes']}))
