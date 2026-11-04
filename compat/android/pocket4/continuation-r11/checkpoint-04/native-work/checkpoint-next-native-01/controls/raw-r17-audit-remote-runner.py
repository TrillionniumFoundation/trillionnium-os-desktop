#!/usr/bin/env python3
"""Bounded read-only audit of the exact r17 build; writes one new audit root."""
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import zipfile

SOURCE = pathlib.Path('/home/alex/work/pocket4-owned-fd-capability-r17-apk-02/fd-owner-probe-r17-source')
BUILD = SOURCE / 'build-attempt-1'
OUTPUT = pathlib.Path('/home/alex/work/pocket4-owned-fd-capability-r17-audit-01')
EXPECTED_BUILD = '401fd328f6997b5b54ee1089b2cf62436824f5cef15f046b53dea6113efdc7e0'
EXPECTED_PINS = 'a24ffd999179df79145a03490c2394d242a96f6d57ab635c41a7da76ac7174eb'
EXPECTED_ELF = '3439433e7e85fae3e95ae67189c9bd3aa29b263266a6da18fe778436023fe4e4'
EXPECTED_APK = '74f54c5b3bb48f4c14a6ea788b7e6df5ba80c4b2944a79be37e99a919f8dab83'
EXPECTED_AUDITOR = 'f403f1d19c139f0f398c7db05c1adc0231802fafdc69d67abc0e48034820d54e'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    OUTPUT.mkdir(exist_ok=False)
    report = {'schema': 1, 'scope': 'Exact Android ELF static worker closure only',
              'qualified_for_owned_runtime_probe': False, 'candidate_production_ready': False,
              'actual_android_executed_by_this_audit': False, 'source_modified': False,
              'writes_confined_to_new_audit_root': str(OUTPUT)}
    try:
        build_file = BUILD / 'build-result.json'
        pins_file = SOURCE / 'SOURCE_PINS.json'
        require(sha(build_file) == EXPECTED_BUILD, 'Build receipt SHA mismatch')
        require(sha(pins_file) == EXPECTED_PINS, 'SOURCE_PINS SHA mismatch')
        build = json.loads(build_file.read_bytes())
        pins = json.loads(pins_file.read_bytes())
        require(build['state'] == 'BUILT_STATIC_VERIFIED_ANDROID_UNRUN', 'Build is not completed')
        require(all(x['returncode'] == 0 for x in build['commands']), 'A build command failed')
        expected = dict(pins['files'], **{'SOURCE_PINS.json': EXPECTED_PINS})
        require(len(expected) == 9 and build['source_sha256'] == expected, 'Nine source pins mismatch')
        before_source = {name: sha(SOURCE / name) for name in expected}
        require(before_source == expected, 'Current sources differ from the completed build')
        script = SOURCE / 'audit_worker_binary.py'
        require(sha(script) == EXPECTED_AUDITOR == expected[script.name], 'Frozen auditor mismatch')
        disassembly = [x for x in build['commands'] if x['name'] == 'disassembly']
        require(len(disassembly) == 1, 'Ambiguous disassembly tool')
        objdump = pathlib.Path(disassembly[0]['argv'][0])
        tool_before = sha(objdump)
        require(build['tools_sha256'][str(objdump)] == tool_before, 'Pinned objdump mismatch')
        elf = BUILD / 'lib/x86_64/libfdownerprobe.so'
        apk = pathlib.Path(build['APK']['path'])
        require(apk.parent == BUILD and apk.name == 'fdownerprobe.apk', 'Unexpected APK path')
        require(disassembly[0]['argv'][-1] == str(elf), 'Disassembly ELF differs')
        require(sha(elf) == EXPECTED_ELF == build['ELF']['sha256'], 'ELF hash mismatch')
        require(sha(apk) == EXPECTED_APK == build['APK']['sha256'], 'APK hash mismatch')
        with zipfile.ZipFile(apk) as archive:
            entries = [x for x in archive.infolist() if x.filename == 'lib/x86_64/libfdownerprobe.so']
            require(len(entries) == 1, 'APK has missing/duplicate ELF')
            zip_elf_sha = hashlib.sha256(archive.read(entries[0])).hexdigest()
        require(zip_elf_sha == EXPECTED_ELF, 'APK ELF differs from audited ELF')
        command = [sys.executable, str(script), str(elf), '--objdump', str(objdump),
                   '--output', str(OUTPUT / 'worker-audit.json')]
        completed = subprocess.run(command, capture_output=True, timeout=40)
        (OUTPUT / 'audit.stdout').write_bytes(completed.stdout)
        (OUTPUT / 'audit.stderr').write_bytes(completed.stderr)
        tool_after = sha(objdump)
        after_source = {name: sha(SOURCE / name) for name in expected}
        require(tool_after == tool_before, 'Objdump changed during audit')
        require(after_source == before_source, 'Sources changed during audit')
        require(sha(elf) == EXPECTED_ELF and sha(apk) == EXPECTED_APK, 'Artifacts changed during audit')
        require(sha(build_file) == EXPECTED_BUILD, 'Build receipt changed during audit')
        worker = json.loads((OUTPUT / 'worker-audit.json').read_text())
        disassembly_text = (OUTPUT / 'worker-audit.disassembly.txt').read_text()
        wanted = set(worker['reachable_functions']) | {'pocket4_raw_clone_x86_64',
                                                      'pocket4::raw_metadata_owner::Start()'}
        relevant = []
        selected = False
        for line in disassembly_text.splitlines():
            match = re.match(r'^\s*[0-9a-f]+ <(.+)>:$', line)
            if match:
                selected = match[1] in wanted
            if selected:
                relevant.append(line)
        relevant_text = '\n'.join(relevant) + '\n'
        require(len(relevant_text.encode()) <= 65536, 'Relevant disassembly exceeds review bound')
        (OUTPUT / 'worker-relevant-disassembly.txt').write_text(relevant_text)
        (OUTPUT / 'build-result.json').write_bytes(build_file.read_bytes())
        report.update(
            build_result_sha256=EXPECTED_BUILD, build_state=build['state'],
            source_pins_sha256=EXPECTED_PINS, source_files_verified=9,
            source_sha256_before=before_source, source_sha256_after=after_source,
            auditor_sha256=EXPECTED_AUDITOR, audit_argv=command, audit_returncode=completed.returncode,
            objdump=str(objdump), objdump_sha256_before=tool_before, objdump_sha256_after=tool_after,
            objdump_matches_build_tool_pin=True, elf_sha256=EXPECTED_ELF, apk_sha256=EXPECTED_APK,
            apk_embedded_elf_sha256=zip_elf_sha, artifact_hashes_unchanged=True,
            worker_audit_sha256=sha(OUTPUT / 'worker-audit.json'),
            relevant_disassembly_sha256=sha(OUTPUT / 'worker-relevant-disassembly.txt'),
            relevant_disassembly_bytes=len(relevant_text.encode()),
            worker_closure=worker,
            qualified_for_owned_runtime_probe=completed.returncode == 0 and worker['qualified_worker_closure'],
            lifecycle_constraints=[
                'No Bionic pthread registration; no root worker may cross into an app credential generation.',
                'Independent FD table does not isolate credentials, capabilities, root or mount state.',
                'Worker must be stopped before any unqualified credential/root/mount/zygote/retirement transition.',
                'Fixed snapshot primitive only. Factory authentication, provenance projection, runtime hooks and arbitrary callbacks are outside this audit.'
            ])
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
    (OUTPUT / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return 0 if report['qualified_for_owned_runtime_probe'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
