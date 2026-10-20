#!/usr/bin/env python3
"""Read-only final-lock review; executes no project code, compiler or VM."""
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path

ROOT = Path('/workspace/scratch/ae1a8cf05419/trillionnium-os-desktop')
OUT = Path(__file__).resolve().parent
E = ROOT / 'support/build/evidence'
inputs = []
checks = []

def read(path):
    path = Path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        a = os.fstat(fd)
        data = b''
        while True:
            chunk = os.read(fd, 1048576)
            if not chunk:
                break
            data += chunk
        b = os.fstat(fd)
        c = os.stat(path, follow_symlinks=False)
        key = lambda s: (s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        if key(a) != key(b) or key(b) != key(c) or len(data) != b.st_size:
            raise RuntimeError('input changed: '+str(path))
        inputs.append({'path':str(path),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
                       'fd_identity':list(key(b))})
        return data
    finally:
        os.close(fd)

def load(path):
    return json.loads(read(path))

def eq(name, actual, expected):
    ok = type(actual) is type(expected) and actual == expected
    checks.append({'check':name,'passed':ok,'actual':actual,'expected':expected})
    if not ok:
        raise RuntimeError(name+' mismatch')

def yes(name, actual):
    eq(name, actual, True)

lock_bytes = read(ROOT/'support/upstream-lock.json')
lock = json.loads(lock_bytes)
base = load(OUT/'baseline-upstream-lock.json')
trimmed = copy.deepcopy(lock)
new = trimmed['kernel'].pop('cloud_next_validation_2026_10_17')
for field in ['native_build_environment','reproducible_kernel_build_note']:
    trimmed[field] = base[field]
eq('all fields other than exactly three authorized paths unchanged',trimmed,base)
eq('pinned upstream commit',lock['kernel']['commit'],'c4b7ed575b7b32773475b194d2ad41fb6d03765b')
eq('pinned upstream tree',lock['kernel']['tree'],'96605cf64aeae2d34f29b97e85eff9315fe10a8e')
eq('pinned toolchain',lock['kernel']['toolchain'],'nightly-2026-07-21')
eq('container pin remains null',lock['build_container_digest'],None)
eq('broad reproducible readiness remains false',lock['reproducible_kernel_build_ready'],False)
eq('retained reproduction note exact original',new['prior_reproduction_note'],base['reproducible_kernel_build_note'])
eq('root README byte length',len(read(ROOT/'README.md')),0)
eq('lock README claim',new['root_readme_bytes'],0)

restore = load(E/'2026-10-17-cloud-restore-next/report.json')
eq('actual hostname',new['actual_host']['hostname'],restore['actual_host'])
eq('actual boot ID',new['actual_host']['boot_id'],restore['boot_id'])
actual_host = load(E/'2026-10-17-debug-private-sdk-native/readable/controller/actual-host.json')
eq('actual host full kernel and resource observations',new['actual_host'],actual_host)
eq('signed package count',new['dependency_restore']['signed_packages'],restore['native']['exact_locked_packages'])
eq('native runtime command count',new['dependency_restore']['native_runtime_checks'],restore['native']['native_runtime_commands_exit_zero'])
eq('fixed Rust commands count',new['dependency_restore']['rust_commands'],8+restore['rust']['additional_identity_checks_exit_zero'])
eq('frozen input members',new['dependency_restore']['frozen_input_members'],restore['frozen_regular_members'])
eq('system installation not claimed',new['dependency_restore']['system_package_install'],restore['restrictions']['system_packages_installed'])

n = load(E/'2026-10-17-private-sdk-native/report.json')
q = load(E/'2026-10-17-private-sdk-native/readable/kernel-boot/qemu.json')
commands = load(E/'2026-10-17-private-sdk-native/readable/controller-N2/commands.json')
sdk = load(E/'2026-10-17-private-sdk-native/sdk-bindings.json')
v = new['ordinary_cold_build_and_boot']
eq('N2 source',v['source_commit'],n['producer_commit'])
eq('N2 derived kernel tree',new['derived_kernel_tree'],n['derived_kernel_tree'])
eq('N2 controller count',v['controller_commands'],len(commands))
yes('N2 all controller exits0',all(c['returncode']==0 for c in commands))
eq('N2 279 cold compile lines',v['cold_compiling_lines'],n['compile_lines']['kernel-build'])
eq('N2 zero boot compile lines',v['subsequent_boot_compiling_lines'],n['compile_lines']['kernel-boot'])
eq('N2 absent target',v['target_absent_before_build'],n['cold_target_absent_before_first_build'])
eq('N2 raw QEMU exit',v['qemu_raw_exit'],q['raw_exit_code'])
eq('N2 no timeout',q['timed_out'],False)
for arg,key in [('-kernel','kernel'),('-initrd','initramfs'),('-bios','bios')]:
    eq('N2 '+key+' digest',v[key+'_sha256'],q['artifacts'][arg]['sha256'])
eq('N2 first kernel length',v['kernel_bytes'],n['first_kernel_elf']['size'])
eq('N2 boot kernel length',v['kernel_bytes'],q['artifacts']['-kernel']['size'])
eq('N2 first kernel hash',v['kernel_sha256'],n['first_kernel_elf']['sha256'])
eq('N2 serial digest',v['serial_sha256'],hashlib.sha256(read(E/'2026-10-17-private-sdk-native/readable/kernel-boot/serial.log')).hexdigest())
eq('N2 complete first/loaded bytes observation',v['first_and_loaded_kernel_complete_bytes_equal'],n['first_and_boot_kernel_complete_bytes_equal'])
eq('N2 complete private SDK equality observation',v['two_private_sdks_complete_bytes_equal'],sdk['same_private_sdk_complete_bytes'])
eq('N2 no prelaunch global binary retained',v['global_prelaunch_payload_retained'],sdk['global_prelaunch_binary_payload_retained'])
eq('N2 no global complete-byte claim',sdk['global_complete_before_after_bytes_compared'],False)

d = load(E/'2026-10-17-debug-private-sdk-native/report.json')
dr = load(E/'2026-10-17-debug-private-sdk-native/readable/retry/run/result.json')
dc = load(E/'2026-10-17-debug-private-sdk-native/readable/retry/controller/commands.json')
dt = load(E/'2026-10-17-debug-private-sdk-native/readable/controller/root-completed-tool.json')
v = new['tcp_debug']
eq('D source',v['source_commit'],d['producer_commit'])
eq('D tool session',v['tool_session'],dt['session_id'])
eq('D outer exit',v['outer_exit'],dt['observed_exit_code'])
eq('D controller count',v['controller_commands'],len(dc))
yes('D all controller exits0',all(c['returncode']==0 for c in dc))
eq('D actual177 compile lines',v['compile_lines'],d['compile_lines'])
eq('D no cold claim',v['cold_target_claimed'],d['cold_build_claimed'])
eq('D GDB exit',v['gdb_status'],dr['gdb']['gdb_status'])
eq('D32-byte entry size',v['entry_size'],len(bytes.fromhex(dr['gdb']['runtime_entry_bytes'])))
eq('D runtime entry matches symbol',dr['gdb']['runtime_entry_bytes'],dr['entry_artifact_binding']['symbol_artifact']['entry_bytes'])
eq('D runtime entry matches loaded boot',dr['gdb']['runtime_entry_bytes'],dr['entry_artifact_binding']['boot_artifact']['entry_bytes'])
eq('D raw QEMU exit',v['qemu_raw_exit'],dr['boot']['raw_qemu_exit'])
yes('D detached',dr['gdb']['detached'])
yes('D initial prepare failure retained',dt['earlier_prepare_failed'])

k = load(E/'2026-10-17-ktest-private-sdk-native/report.json')
kr = load(E/'2026-10-17-ktest-private-sdk-native/readable/runner-result.json')
kc = load(E/'2026-10-17-ktest-private-sdk-native/readable/controller-commands.json')
v = new['kernel_mode_tests']
eq('K source',v['source_commit'],k['producer_commit'])
eq('K controller count',v['controller_commands'],len(kc))
yes('K all controller exits0',all(c['returncode']==0 for c in kc))
guests = [g for c in kr['crates'] for g in c['guests']]
for key in ['passed','failed','soft_skipped','exercised_passed_lower_bound']:
    mk = 'reported_passed' if key=='passed' else key
    eq('K '+key+' total',v[mk],sum(g[key] for g in guests))
eq('K raw exits',v['raw_qemu_exits'],[g['raw_qemu_exit'] for g in guests])
eq('K reused target',v['target_reused'],k['target_reused'])
eq('K no cold claim',v['cold_target_claimed'],k['cold_build_claimed'])
eq('K no immutable execution claim',k['immutable_execution_claimed'],False)
eq('K no prelaunch snapshot execution claim',k['snapshot_loaded_execution_claimed'],False)
for crate in ['ostd','aster-core']:
    sq = load(E/('2026-10-17-ktest-private-sdk-native/readable/run/'+crate+'/guests/guest-001/qemu.json'))
    eq('K '+crate+' original raw QEMU status',sq['raw_exit_code'],33)
    eq('K '+crate+' no timeout',sq['timed_out'],False)

c = load(E/'2026-10-17-repro-cross-instance/comparison.json')
l = load(E/'2026-10-17-repro-cross-instance/live-comparison.json')
v = new['observed_cross_instance_reproduction']
eq('cross-instance producer',v['source_commit'],c['source_commit'])
eq('two observed case IDs',v['cases'],[x['case'] for x in c['cases']])
eq('two observed hostnames',v['actual_hostnames'],[x['actual_host']['hostname'] for x in c['cases']])
yes('all three actual complete byte comparisons',all(l['complete_input_bytes_equal'].values()) and l['all_complete_bytes_compared'])
eq('canonical descriptor equality bool',v['canonical_descriptors_equal'],c['canonical_local_descriptors_equal'])
eq('producer identities/counts equality',v['cargo_producer_identity_counts_equal'],c['cargo_producer_identity_counts_equal'])
yes('canonical descriptor maps independently equal',c['cases'][0]['canonical_local_descriptors_sha256']==c['cases'][1]['canonical_local_descriptors_sha256'])
yes('cargo producer key/count maps independently equal',c['cases'][0]['cargo_producer_identity_counts']==c['cases'][1]['cargo_producer_identity_counts'])
for case in c['cases']:
    eq(case['case']+' canonical descriptors61',v['canonical_descriptor_count'],case['canonical_local_descriptors'])
    eq(case['case']+' full ELF digest',v['kernel_sha256'],case['inputs']['-kernel']['sha256'])
    eq(case['case']+' full ELF byte length',v['kernel_bytes'],case['inputs']['-kernel']['bytes'])
    eq(case['case']+' raw exit',case['raw_qemu_exit'],33)
for field in ['arbitrary_host_reproduction_claimed','immutable_environment_claimed','provider_instance_attestation_claimed']:
    eq('bounded reproduction '+field,v[field],False)
eq('same literal dependency/profile environment',c['cases'][0]['fixed_environment'],c['cases'][1]['fixed_environment'])
eq('five NEW guests excludes historical A4',new['current_round_real_qemu_guests'],1+1+1+len(guests))
eq('five new raw QEMU exits',new['current_round_raw_qemu_exits'],[c['cases'][1]['raw_qemu_exit'],q['raw_exit_code'],dr['boot']['raw_qemu_exit']]+[g['raw_qemu_exit'] for g in guests])
eq('host ordinary check sum161',new['normal_private_sdk']['host_test_executions'],40+40+40+9+32)
for key in ['native_resource_control_accepted','default_unix_gdb_supported_on_this_host','vmx_ept_exercised','unknown_workspace_writer_identified','all_project_blockers_closed']:
    eq('bounded/open '+key,new[key],False)
eq('lock unchanged across read-only review',read(ROOT/'support/upstream-lock.json'),lock_bytes)

# Remove bulky actual/expected equal dictionaries and bytes from the public receipt.
for item in checks:
    for key in ['actual','expected']:
        value=item[key]
        if isinstance(value,(dict,list,bytes)) and len(str(value))>1000:
            item[key]={'type':type(value).__name__,'equal_value_omitted':True}
receipt={'schema':'a01-independent-final-metadata-review/1',
         'observed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
         'lock_sha256':hashlib.sha256(lock_bytes).hexdigest(),
         'baseline_commit':'1001161c45fed52b4735606c81bc039cad770db4',
         'passed':True,'checks':checks,'inputs':inputs,
         'scope':'Read-only scalar/custody fact checks of completed evidence, no project code execution, no compile or VM. Existing source/report acceptance remains tied to original producer commits.'}
print(json.dumps(receipt,indent=2))
