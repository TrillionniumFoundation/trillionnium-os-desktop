from pathlib import Path
import hashlib,json
D=Path('/data/asterinas-audit-build.8tdrjboi'); O=D/'socket-credential-native-22e0-01'; W=D/'socket-credential-snapshot-receipt'
A=Path('/data/asterinas-dumpable-audit-01.yswd2fi4')
def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
p=read(O/'pipeline.json'); assert p['complete'] and p['passed'] and p['source_checkout_clean']
ret=read(O/'full/retention.json'); assert ret['source_unchanged'] and ret['source_head']==p['source_head']
r={'schema':'trillionnium.unix-socket-credential-snapshot-qualified.v1','source_head':p['source_head'],'source_tree':p['source_tree'],'source_unchanged':True,'evidence_root':str(O),'elapsed_seconds':p['elapsed_seconds'],'full_suites':[]}
for crate in ['ostd','osdk-frame-allocator','aster-core','aster-mlsdisk']:
 a=read(O/'full/ktest'/crate/'result.json'); assert a['passed']; g=a['guests'][0]
 assert g['raw_qemu_exit']==33 and g['failed']==0 and g['filtered']==0
 assert g['declared']=={'ostd':230,'osdk-frame-allocator':20,'aster-core':365,'aster-mlsdisk':15}[crate]
 item={k:g[k] for k in ['crate','declared','passed','failed','filtered','soft_skipped','soft_skip_reasons','raw_qemu_exit']}
 item.update(required_core_tests=len(g['required_core_tests']),required_ostd_tests=len(g['required_ostd_tests']),kernel_sha256=ret['crates'][crate]['kernel']['sha256'],serial_sha256=ret['crates'][crate]['serial_sha256']);r['full_suites'].append(item)
o=read(O/'ordinary/result.json'); assert o['passed'] and o['source_head']==p['source_head'] and o['source_tree']==p['source_tree'] and o['source_inputs_unchanged']
r['ordinary']={k:o[k] for k in ['passed','source_head','source_tree','kernel_elf_sha256','marker_counts','qemu_exit','source_inputs_unchanged','source_file_count']}
for name in ['sgid30','ownership12','proc-privileges12','memfd4','signal22']:
 a=read(O/name/'result.json'); key='raw_qemu_exit' if name in ['sgid30','proc-privileges12'] else 'qemu_exit'
 assert a['passed'] and a[key]==33 and not a['timed_out'] and a['kernel_sha256']==o['kernel_elf_sha256']
 assert len(a['cases'])=={'sgid30':30,'ownership12':12,'proc-privileges12':12,'memfd4':4,'signal22':22}[name]
 r[name]={k:a[k] for k in ['passed','cases','timed_out','kernel_sha256','probe_sha256','probe_source_sha256']}; r[name]['raw_qemu_exit']=a[key]
for name,count in [('lifecycle',164),('stat',54),('traceme',15)]:
 a=read(O/name/'result.json'); assert a['passed'] and a['qemu_exit']==33 and not a['timed_out']
 assert a['kernel_sha256']==o['kernel_elf_sha256'] and a['oracle']['observations']==count and a['oracle']['all_children_reaped']
 r[name]={k:a[k] for k in ['passed','oracle','qemu_exit','timed_out','elapsed_seconds','kernel_sha256','probe_sha256','probe_source_sha256','serial_sha256']}
paths=['pipeline.json','full/outer-result.json','full/osdk-retention.json','full/retention.json','full/source-before.json','full/source-after.json','ordinary/result.json']
for n in ['sgid30','ownership12','proc-privileges12','memfd4','signal22','lifecycle','stat','traceme']: paths += [n+'/result.json',n+'/serial.log']
for n in ['ownership12','memfd4','signal22','lifecycle','stat','traceme']: paths += [n+'-source-bound.json',n+'-source-after.json']
r['retained_receipts']=[{'path':str(O/f),'sha256':sha(O/f)} for f in paths]

a=read(O/'dac6/result.json'); assert a['passed'] and a['qemu_exit']==33 and not a['timed_out'] and len(a['oracle']['cases'])==6 and a['oracle']['all_children_reaped']
assert a['kernel_sha256']==o['kernel_elf_sha256']
r['dac6']={k:a[k] for k in ['passed','oracle','qemu_exit','timed_out','elapsed_seconds','kernel_sha256','probe_sha256','probe_source_sha256','serial_sha256','linux_audit_receipt_sha256']}
for f in ['dac6/result.json','dac6/serial.log','dac6-source-bound.json','dac6-source-after.json']:
 r['retained_receipts'].append({'path':str(O/f),'sha256':sha(O/f)})
A=D/'commoncap-owned-audit-01'
r['original_reference_and_negative']=[{'path':str(A/f),'sha256':sha(A/f)} for f in ['linux-reference.json','linux-reference.jsonl','commoncap_probe.c','native-690a-baseline-01/result.json','native-690a-baseline-01/serial.log']]
r['host_checks']=[{'path':str(D/f),'sha256':sha(D/f)} for f in ['socket-credential-host-full-01.log','socket-credential-source-gate-02.json','socket-credential-clippy-03.log','socket-credential-g1d-clippy-02.log','socket-credential-checker-02.log']]
r['earlier_host_checks']=[{'path':str(D/f),'sha256':sha(D/f)} for f in ['socket-credential-clippy-01.log','socket-credential-clippy-02.log','socket-credential-g1d-clippy-01.log','socket-credential-checker-01.log']]
r['profile']={'memory_mib':512,'vcpus':1,'core_acceleration':'tcg','dac_acceleration':'kvm','ktest_guest_deadline_seconds':300,'probe_guest_deadline_seconds':120,'filtered_suite':False}
r.update(production_authority=False,global_recovery_guarantee=False,all_kernel_memory_accounted=False,full_linux_permission_parity=False)
import re
serial=O/'full/ktest/aster-core/guests/guest-001/serial.log'
matched=re.findall(rb'VMAR_PHYSICAL_PT_NOMEMORY held_frames=(\d+) ordinary_4k_windows=0,1,2 unpublished_nodes_refunded=0,1,2 recovered=true global_recovery_guarantee=false', serial.read_bytes())
assert len(matched)==1 and int(matched[0])>8
r['physical_pt_nomemory']={'ordinary_4k_available_windows':[0,1,2],'unpublished_nodes_refunded':[0,1,2],'held_frames':int(matched[0]),'no_quota_or_injection':True,'original_vmar_fault':True,'original_mapping_rss_family_ancestor_unchanged':True,'recovery_after_pressure_release':True,'final_reference_refund':True,'heap_bookkeeping_allocated_before_pressure':True,'physical_free_bytes_zero_claimed':False,'serial_sha256':sha(serial)}
a=read(O/'commoncap16/result.json'); assert a['passed'] and a['qemu_exit']==33 and not a['timed_out'] and a['oracle']['cases']==16 and a['oracle']['all_children_reaped']
assert a['kernel_sha256']==o['kernel_elf_sha256']
r['commoncap16']={k:a[k] for k in ['passed','oracle','qemu_exit','timed_out','elapsed_seconds','kernel_sha256','probe_sha256','probe_source_sha256','serial_sha256','linux_audit_receipt_sha256']}
for f in ['commoncap16/result.json','commoncap16/serial.log','commoncap16-source-bound.json','commoncap16-source-after.json']:
 r['retained_receipts'].append({'path':str(O/f),'sha256':sha(O/f)})
for name,count in [('credentials59',59),('groups16',16)]:
 a=read(O/name/'result.json'); assert a['passed'] and a['qemu_exit']==33 and not a['timed_out'] and a['oracle']['observations']==count and a['oracle']['all_children_reaped']
 assert a['kernel_sha256']==o['kernel_elf_sha256']
 r[name]={k:a[k] for k in ['passed','oracle','qemu_exit','timed_out','elapsed_seconds','kernel_sha256','probe_sha256','probe_source_sha256','serial_sha256','linux_audit_receipt_sha256']}
 for f in [name+'/result.json',name+'/serial.log',name+'-source-bound.json',name+'-source-after.json']:
  r['retained_receipts'].append({'path':str(O/f),'sha256':sha(O/f)})
A=D/'socket-credential-lifetime-audit-01'
r['socket_original_references_and_negatives']=[{'path':str(A/f),'sha256':sha(A/f)} for f in ['linux-reference-01.json','linux-reference-01.jsonl','v1/socket_credential_probe.c','v1/socket-credential-probe','linux-reference-02.json','linux-reference-02.jsonl','socket_credential_probe.c','socket-credential-probe','group-linux-reference-01.json','group-linux-reference-01.jsonl','socket_group_probe.c','socket-group-probe','native-4aab-baseline-01/result.json','native-4aab-baseline-01/serial.log','native-4aab-baseline-02/result.json','native-4aab-baseline-02/serial.log','native-group-4aab-baseline-01/result.json','native-group-4aab-baseline-01/serial.log','socket_credential_probe_compile_negative_01.c','compile-01.log']]
r['feature_compile_only']={'feature':'g1d-trusted-control','native_qualification':False,'compile_time_initial_image':str(D/'watchdog-native-960-01/g1d-init'),'compile_time_initial_image_sha256':sha(D/'watchdog-native-960-01/g1d-init')}
r['remaining_socket_limits']={'msg_dontwait_datagram_supported':False,'general_heap_recovery':False,'complete_privileged_scm_credentials_parity':False,'peer_credential_identifies_current_fd_holder':False,'original_group_set_construction_fallible':False}
r['scope']='Original SocketCred captures real/effective identity scalars and original immutable supplementary-group Arc; original credential owner replaces group Arc under its spin lock and drops old outside lock. Two real owner kernel tests plus unchanged Linux-referenced 59-record lifetime and 16-record group probes; all original native gates re-executed. Existing actual SCM_CREDENTIALS validation preserved. MSG_DONTWAIT datagram defect remains independently open; O_NONBLOCK v2 fixture does not qualify it. No production Root/Host authority, complete Linux credential parity, or global memory recovery qualification.'
(W/'results/integration/2026-10-23-audit-closure/socket-credential-22e0.json').write_text(json.dumps(r,indent=2)+'\n')
print(p['source_head'],p['elapsed_seconds'],o['kernel_elf_sha256'],r['credentials59'],r['groups16'])
