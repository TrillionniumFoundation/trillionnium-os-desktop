# SPDX-License-Identifier: MPL-2.0
"""Closed sixteen-operation original-credential oracle; no guest authority claim."""
import json
import re

OPERATIONS = ('maps', 'mem', 'environ', 'auxv', 'fd', 'exe', 'ns/mnt', 'pidfd_getfd_dev_null')


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value: raise ValueError('duplicate key')
        value[key] = item
    return value


def check(raw, code, timed_out):
    passed = False
    try:
        if isinstance(raw, bytes): raw = raw.decode('utf-8', errors='strict')
        if type(raw) is not str or len(raw.encode()) > 2*1024*1024: raise ValueError('size/type')
        if type(code) is not int or code != 33 or timed_out is not False: raise ValueError('completion')
        lines = re.sub(r'\x1b\[[0-9;]*m', '', raw).replace('\r', '').splitlines()
        selected = [line for line in lines if line.startswith(('{', 'COMMONCAP_'))]
        if selected[-1] != 'COMMONCAP_PROBE_EXIT=0': raise ValueError('exit')
        boot = [i for i, line in enumerate(lines) if 'TRILLIONNIUM_A01_BOOT_OK' in line]
        if len(boot) != 1 or lines[boot[0]] != 'TRILLIONNIUM_A01_BOOT_OK': raise ValueError('boot')
        if lines.index(selected[-1]) >= boot[0]: raise ValueError('order')
        if any(token in raw.lower() for token in ('panicked at', 'kernel panic')): raise ValueError('panic')
        rows = [json.loads(line, object_pairs_hook=_object) for line in selected[:-1]]
        def exact(expected):
            row = rows.pop(0)
            if row.keys() != expected.keys() or any(type(row[k]) is not type(v) or row[k] != v for k,v in expected.items()):
                raise ValueError('exact record')
        def case(name): exact({'case': name, 'passed': True})
        exact({'suite':'owned-commoncap-v1','maximum_live_children':1,'production_qualified':False})
        exact({'observer_uid':60001,'observer_euid':60001,'effective':0,'permitted':0,'nnp':1,'setup_error':0})
        case('observer_actual_caps0_nnp1'); case('owned_child_pidfd')
        fd_name = None
        for stage, denied in [('target_extra_permitted', True), ('same_permitted', False)]:
            exact({'target_stage':stage,'uid':60001,'euid':60001,'gid':60001,'egid':60001,
                   'effective':0,'permitted':int(denied),'dumpable':1,'nnp':1,'setup_error':0})
            case('target_actual_identity_and_caps')
            for op in OPERATIONS:
                row = rows.pop(0)
                if set(row) != {'stage','operation','rc','errno','denied_expected','passed'}: raise ValueError('operation fields')
                if row['stage'] != stage or type(row['stage']) is not str: raise ValueError('stage')
                if op == 'fd':
                    if type(row['operation']) is not str or not re.fullmatch(r'fd/[0-9]+',row['operation']): raise ValueError('fd')
                    if fd_name is None: fd_name = row['operation']
                    if row['operation'] != fd_name: raise ValueError('changed fd')
                elif row['operation'] != op: raise ValueError('operation order')
                if row['denied_expected'] is not denied or row['passed'] is not True: raise ValueError('claim')
                rc, error = row['rc'], row['errno']
                if type(rc) is not int or type(error) is not int: raise ValueError('numeric type')
                if denied:
                    if rc != -1 or error not in (1,13): raise ValueError('real permission denial')
                else:
                    expected = 4 if op == 'mem' else 1 if op in ('maps','environ','auxv','pidfd_getfd_dev_null') else None
                    if error != 0 or (rc != expected if expected is not None else not 0 < rc <= 512): raise ValueError('positive read')
                    if op == 'mem': case('only_public_sentinel_read')
                    if op == 'pidfd_getfd_dev_null': case('copied_only_owned_dev_null')
        case('owned_child_reaped')
        exact({'summary':True,'failures':0,'setup_unavailable':False,'all_children_reaped':True})
        if rows: raise ValueError('extra records')
        passed = True
    except (ValueError, TypeError, IndexError, KeyError, UnicodeError):
        pass
    return {'passed':passed,'cases':16 if passed else 0,'all_children_reaped':passed,
            'raw_qemu_exit':code,'timed_out':timed_out,'production_qualification':False}
