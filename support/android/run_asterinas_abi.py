#!/usr/bin/env python3
"""Run A08 ABI initramfs on A01-built Asterinas in isolated QEMU/TCG.

Requires an actual A01 kernel ELF plus its measured SHA256. Reuses A01's
recorded safe single-CPU QEMU command shape without touching kernel sources.
Results never qualify Binder transactions, ART, Android APKs or hardware.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ABI_TESTS = ("mmap", "memfd_create", "SCM_RIGHTS", "futex_wait_wake", "signal")
BINDER_PRIMITIVES = ("binder_protocol_version", "binder_set_max_threads",
                     "binder_mmap", "binder_empty_write_read")
REQUIRED = ("TRILLIONNIUM_A01_INIT_BEGIN", "A08_GUEST_ABI_BEGIN",
            "A08_GUEST_ABI_PASS", "A08_GUEST_SECCOMP_BEGIN",
            "A08_GUEST_SECCOMP_END", "A08_GUEST_ABI_END",
            "TRILLIONNIUM_A01_BOOT_OK")
FATAL_PANIC = ("panicked at", "An uncaught panic occurred:", "Uncaught panic:",
               "Non-resettable panic!", "PanicGuard", "Kernel panic - not syncing")
VALUE_FLAGS = ('-kernel','-initrd','-append','-machine','-accel','-cpu',
               '-bios','-m','-smp','-display','-monitor','-serial','-chardev','-device')
SWITCH_FLAGS = ('-nodefaults','-no-user-config','-no-reboot','-nographic')


def sha(path:Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def safe_argv(record:dict, *, kernel:Path, initramfs:Path, bios:Path,
              qemu:Path, log:Path) -> list[str]:
    args=record.get('argv')
    if not isinstance(args,list) or not args or not all(isinstance(x,str) for x in args):
        raise ValueError('recorded A01 QEMU argv is missing/invalid')
    i=1
    while i<len(args):
        opt=args[i]
        if opt in SWITCH_FLAGS:
            i+=1
        elif opt in VALUE_FLAGS and i+1<len(args):
            i+=2
        else:
            raise ValueError('QEMU template contains unknown/unsafe host option: '+opt)
    for flag,value in (('-machine','q35'),('-accel','tcg'),('-cpu','max'),
                       ('-m','512M'),('-smp','1'),('-serial','chardev:serial'),
                       ('-device','isa-debug-exit,iobase=0xf4,iosize=0x04'),
                       ('-display','none'),('-monitor','none')):
        if args.count(flag)!=1 or args[args.index(flag)+1]!=value:
            raise ValueError('A01 TCG profile mismatch: '+flag)
    for flag in ('-kernel','-initrd','-bios','-chardev'):
        if args.count(flag)!=1:
            raise ValueError('missing/duplicated QEMU '+flag)
    for flag in ('-nodefaults','-no-user-config','-no-reboot','-nographic'):
        if args.count(flag)!=1:
            raise ValueError('missing required isolation flag '+flag)
    serial=args[args.index('-chardev')+1]
    if serial != 'stdio,id=serial,signal=off,logfile=qemu.log':
        raise ValueError('QEMU serial chardev is not the exact A01 logging profile')
    if args.count('-append') != 1:
        raise ValueError('A01 QEMU profile requires exactly one kernel command line')
    cmdline = args[args.index('-append') + 1].split()
    allowed = {'earlycon', 'console=ttyS0', 'loglevel=info',
               'SHELL=/bin/sh', 'LOGNAME=root', 'HOME=/', 'USER=root',
               'PATH=/bin:/sbin', '--'}
    if 'console=ttyS0' not in cmdline or any(value not in allowed for value in cmdline):
        raise ValueError('unsafe or unrecognized A01 QEMU kernel command line')
    if ',' in str(log.resolve()) or '\n' in str(log.resolve()):
        raise ValueError('serial evidence path is not safe for QEMU chardev')
    out=list(args)
    out[0]=str(qemu.resolve())
    for flag,path in (('-kernel',kernel),('-initrd',initramfs),('-bios',bios)):
        out[out.index(flag)+1]=str(path.resolve())
    out[out.index('-chardev')+1]='stdio,id=serial,signal=off,logfile='+str(log.resolve())
    return out


def assess(exit: int | None, serial: str) -> dict:
    """Reject forged/partial PASS markers; retain each syscall and Binder result.

    The kernel-ABI smoke must emit an actual successful line for *every* named
    syscall. A shell success marker or exit=33 alone cannot claim a target ABI
    pass. Binder device open, ioctl/mmap, and full transactions remain distinct.
    """
    lines = [line.strip() for line in serial.splitlines()]
    errors: list[str] = []
    positions: dict[str, int] = {}
    for marker in REQUIRED:
        hits = [i for i, line in enumerate(lines) if line == marker]
        if len(hits) != 1:
            errors.append(f"marker_{marker}_{'missing' if not hits else 'duplicated'}")
        else:
            positions[marker] = hits[0]
    if len(positions) == len(REQUIRED) and list(positions.values()) != sorted(positions.values()):
        errors.append('guest_marker_order_invalid')
    if exit != 33:
        errors.append('qemu_raw_exit_not_33')
    if any(token in line for line in lines for token in FATAL_PANIC):
        errors.append('kernel_panic_in_serial')
    if any(line.startswith('A08_GUEST_ABI_FAIL:') for line in lines):
        errors.append('guest_abi_exit_nonzero')

    abi_start = positions.get('A08_GUEST_ABI_BEGIN', -1)
    abi_end = positions.get('A08_GUEST_ABI_PASS', len(lines))
    abi_lines = lines[abi_start + 1:abi_end] if 0 <= abi_start < abi_end else []
    measurements: dict[str, dict] = {}
    for name in ABI_TESTS:
        matches = [re.fullmatch(re.escape(name) + r'\t([A-Z_]+)\terrno=(\d+)', line)
                   for line in abi_lines]
        found = [m for m in matches if m]
        if len(found) != 1:
            errors.append(f'abi_{name}_' + ('missing' if not found else 'duplicated'))
            measurements[name] = {'status': 'missing_or_duplicated'}
            continue
        status, errno = found[0].group(1), int(found[0].group(2))
        measurements[name] = {'status': status, 'errno': errno}
        if status != 'PASS' or errno != 0:
            errors.append(f'abi_{name}_not_pass')
    headers = [re.fullmatch(r'# host=syscall_probe page_size=(\d+) uid=(\d+)', line)
               for line in abi_lines]
    host = [m for m in headers if m]
    if len(host) != 1 or int(host[0].group(1)) != 4096:
        errors.append('guest_page_size_not_4096_or_missing')
    binder_initial = [re.fullmatch(r'binder_device_open\t([A-Z_]+)\terrno=(\d+)', line)
                      for line in abi_lines]
    binder_initial = [m for m in binder_initial if m]
    if len(binder_initial) != 1:
        errors.append('binder_initial_device_probe_missing_or_duplicated')

    binder_start = positions.get('A08_GUEST_ABI_PASS', -1)
    binder_end = positions.get('A08_GUEST_ABI_END', len(lines))
    binder_region = lines[binder_start + 1:binder_end] if 0 <= binder_start < binder_end else []
    binder_markers = [line for line in binder_region
                      if line == 'A08_GUEST_BINDER_PRIMITIVES_PASS' or
                      line.startswith('A08_GUEST_BINDER_EXIT:')]
    binder = 'not_executed'
    if len(binder_markers) != 1:
        errors.append('binder_result_marker_missing_or_duplicated')
    else:
        binder_marker = binder_markers[0]
        if binder_marker == 'A08_GUEST_BINDER_PRIMITIVES_PASS':
            failures = []
            for name in BINDER_PRIMITIVES:
                statuses = [line for line in binder_region
                            if line.startswith(name + '\t')]
                if statuses != [name + '\tPASS\terrno=0']:
                    failures.append(name)
            if failures or not any('binder_transactions\tNOT_TESTED' in line
                                   for line in binder_region):
                binder = 'unproven_primitives'
                errors.append('binder_primitive_details_missing_or_failed')
            elif (len(binder_initial) == 1 and
                  binder_initial[0].group(1) != 'PRESENT_UNVERIFIED'):
                binder = 'inconsistent_open_status'
                errors.append('binder_open_status_inconsistent')
            else:
                binder = 'primitive_ioctl_mmap_only'
        else:
            match = re.fullmatch(r'A08_GUEST_BINDER_EXIT:(\d+)', binder_marker)
            if not match:
                binder = 'malformed_exit'
                errors.append('binder_bad_exit_code_marker')
            elif int(match.group(1)) == 77:
                blocked = [re.fullmatch(r'binder_device_open\tBLOCKED\terrno=(\d+)',line)
                           for line in binder_region]
                blocked = [m for m in blocked if m]
                if len(blocked) != 1 or int(blocked[0].group(1)) == 0:
                    binder = 'unproven_open_failure'
                    errors.append('binder_open_errno_evidence_missing')
                elif (len(binder_initial) == 1 and
                      binder_initial[0].group(1) != 'BLOCKED'):
                    binder = 'inconsistent_open_status'
                    errors.append('binder_open_status_inconsistent')
                else:
                    binder = 'blocked_no_device' if int(blocked[0].group(1)) in (2, 19) else 'blocked_access'
            else:
                binder = 'probe_failed'
    seccomp_start = positions.get('A08_GUEST_SECCOMP_BEGIN', -1)
    seccomp_end = positions.get('A08_GUEST_SECCOMP_END', len(lines))
    seccomp_lines = lines[seccomp_start+1:seccomp_end] if 0 <= seccomp_start < seccomp_end else []
    seccomp_markers = [line for line in seccomp_lines
                       if line == 'A08_GUEST_SECCOMP_FILTER_PASS' or
                       line.startswith('A08_GUEST_SECCOMP_EXIT:')]
    seccomp_status = 'not_executed'
    seccomp_install_errno = None
    seccomp_observed = {}
    if len(seccomp_markers) != 1:
        errors.append('seccomp_result_marker_missing_or_duplicated')
    elif seccomp_markers[0] == 'A08_GUEST_SECCOMP_FILTER_PASS':
        # A child-restricted BPF filter must genuinely reject getpid and
        # allow getppid. A success marker alone is never enough.
        expected = ('no_new_privs', 'seccomp_filter_install',
                    'seccomp_deny_getpid', 'seccomp_allow_getppid')
        for name in expected:
            matched = [line for line in seccomp_lines if line.startswith(name+'\t')]
            seccomp_observed[name] = matched
        child = [line for line in seccomp_lines if line.startswith('seccomp_child\t')]
        if (any(seccomp_observed[n] != [n+'\tPASS\terrno=0'] for n in expected) or
                child != ['seccomp_child\tPASS\texit=0'] or
                seccomp_lines.count('seccomp_TSYNC_multithread\tNOT_TESTED\terrno=0') != 1 or
                seccomp_lines.count('Android_process_filters\tNOT_TESTED\terrno=0') != 1):
            seccomp_status = 'unproven_filter_enforcement'
            errors.append('seccomp_filter_details_missing_or_failed')
        else:
            seccomp_status = 'filter_enforcement_primitive_only'
    else:
        m = re.fullmatch(r'A08_GUEST_SECCOMP_EXIT:(\d+)', seccomp_markers[0])
        if not m:
            seccomp_status = 'malformed_exit'
            errors.append('seccomp_exit_marker_invalid')
        else:
            exit_code = int(m.group(1))
            installs = [re.fullmatch(r'seccomp_filter_install\tFAIL\terrno=(\d+)',line)
                        for line in seccomp_lines]
            installs = [item for item in installs if item]
            if exit_code == 13 and len(installs) == 1 and int(installs[0].group(1)) != 0:
                seccomp_install_errno = int(installs[0].group(1))
                seccomp_status = ('filter_install_not_implemented' if seccomp_install_errno in (38, 95)
                                  else 'filter_install_denied')
            elif (exit_code == 77 and
                  seccomp_lines.count('seccomp_syscall_available\tUNSUPPORTED_BUILD\terrno=0') == 1):
                seccomp_status = 'unsupported_probe_build'
            else:
                seccomp_status = 'probe_failed'
    # A seccomp gap is an independent Android blocker, not proof that the
    # already-measured mmap/futex/etc. syscalls failed. Missing/forged
    # seccomp evidence is invalid whole-guest instrumentation, however.
    return {
        'linux_abi_probe': 'pass' if not errors else 'fail',
        'binder_probe': binder, 'seccomp_probe': seccomp_status,
        'seccomp_filter_install_errno': seccomp_install_errno,
        'seccomp_tsync_verified': False, 'android_seccomp_filters_verified': False,
        'abi_syscalls': measurements,
        'guest_page_size_bytes': int(host[0].group(1)) if len(host) == 1 else None,
        'markers': {name: name in positions for name in REQUIRED},
        'failure_reasons': errors, 'raw_qemu_exit': exit,
        'android_runtime_verified': False,
        'binder_full_transactions_verified': False,
    }

def execute(template:Path,kernel:Path,kernel_sha:str,initrd:Path,manifest:Path,
            bios:Path,qemu:Path,outdir:Path,timeout:int=180)->dict:
    if outdir.exists():
        raise ValueError('evidence directory exists; refusing to overwrite evidence')
    if not isinstance(timeout, int) or not 1 <= timeout <= 600:
        raise ValueError('QEMU timeout must be between 1 and 600 seconds')
    if not re.fullmatch(r'[a-f0-9]{64}',kernel_sha) or sha(kernel)!=kernel_sha:
        raise ValueError('kernel ELF SHA256 does not match trusted A01 build')
    m=json.loads(manifest.read_text())
    if m.get('kind')!='a08_asterinas_abi_initramfs' or sha(initrd)!=m.get('image_sha256'):
        raise ValueError('initramfs image does not match A08 measured manifest')
    if not bios.is_file() or not qemu.is_file():
        raise ValueError('QEMU or SeaBIOS missing; no guest run attempted')
    cfg=json.loads(template.read_text())
    assets=cfg.get('artifacts',{})
    if (assets.get('-kernel',{}).get('sha256')!=kernel_sha or
            assets.get('-bios',{}).get('sha256')!=sha(bios)):
        raise ValueError('kernel/SeaBIOS differ from the recorded A01 QEMU evidence')
    if cfg.get('raw_exit_code') != 33 or cfg.get('timed_out') is not False:
        raise ValueError('A01 source QEMU record has no verified success exit')
    if cfg.get('qemu_sha256') != sha(qemu):
        raise ValueError('QEMU binary differs from the recorded A01 executable')
    qemu_version=subprocess.run([str(qemu),'--version'],capture_output=True,
        text=True,check=False,timeout=10)
    if qemu_version.returncode!=0 or not qemu_version.stdout.startswith('QEMU emulator version'):
        raise ValueError('QEMU binary identity/version probe failed')
    log=outdir/'serial.log'
    args=safe_argv(cfg,kernel=kernel,initramfs=initrd,bios=bios,qemu=qemu,log=log)
    outdir.mkdir(parents=True)
    report={'schema':1,'scope':'Asterinas QEMU TCG x86_64 guest Linux ABI',
            'android_runtime_verified':False,'qemu_args':args,
            'kernel_sha256':kernel_sha,'initramfs_sha256':sha(initrd),
            'bios_sha256':sha(bios),'qemu_binary_sha256':sha(qemu),
            'qemu_exit':None}
    try:
        p=subprocess.run(args,cwd=outdir,capture_output=True,
                         check=False,timeout=timeout)
        report['qemu_exit']=p.returncode
        (outdir/'stdout.log').write_bytes(p.stdout)
        (outdir/'stderr.log').write_bytes(p.stderr)
    except (OSError,subprocess.TimeoutExpired) as exc:
        report['error']=str(exc)
    serial_bytes=log.read_bytes() if log.is_file() else b''
    serial=serial_bytes.decode(errors='replace')
    report['serial_sha256']=hashlib.sha256(serial_bytes).hexdigest()
    report['result']=assess(report['qemu_exit'],serial)
    (outdir/'result.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    return report


def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--a01-qemu-json',type=Path,required=True)
    p.add_argument('--kernel',type=Path,required=True)
    p.add_argument('--expected-kernel-sha256',required=True)
    p.add_argument('--initramfs',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--bios',type=Path,required=True)
    p.add_argument('--qemu',type=Path,required=True)
    p.add_argument('--outdir',type=Path,required=True)
    p.add_argument('--timeout',type=int,default=180)
    a=p.parse_args(argv)
    try:
        r=execute(a.a01_qemu_json,a.kernel,a.expected_kernel_sha256,
                  a.initramfs,a.manifest,a.bios,a.qemu,a.outdir,a.timeout)
        status=r['result']
        print(json.dumps(status))
        return 0 if (status['linux_abi_probe']=='pass' and
                     status['binder_probe']=='primitive_ioctl_mmap_only' and
                     status['seccomp_probe']=='filter_enforcement_primitive_only') else 2
    except (OSError,ValueError) as exc:
        print('A08 target ABI guest blocked: '+str(exc),file=sys.stderr)
        return 3

if __name__=='__main__':sys.exit(main())
