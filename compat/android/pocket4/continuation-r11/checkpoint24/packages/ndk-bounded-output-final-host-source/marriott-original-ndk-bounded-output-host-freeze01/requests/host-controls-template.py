#!/usr/bin/env python3
"""Fixed host-only regression envelope; no Main, Android or namespace entry."""
import base64
import hashlib
import json
import os
import sys

PACKET_B64=None
PACKET_PIN=None
MAX_PACKET=524288
MAX_OUTPUT=131072


def need(value,code):
    if not value:
        raise RuntimeError(code)


def main():
    raw=base64.b64decode(PACKET_B64,validate=True)
    need(type(PACKET_PIN) is dict and set(PACKET_PIN)=={'bytes','sha256'} and
         len(raw)==PACKET_PIN['bytes']<=MAX_PACKET and
         hashlib.sha256(raw).hexdigest()==PACKET_PIN['sha256'],'EXACT_FIXED_CONTROLS_PACKET')
    packet=json.loads(raw)
    need(type(packet) is dict and set(packet)=={'schema','kind','members'} and
         packet['schema']==1 and packet['kind']=='p4-ndk-bounded-output-host-controls01' and
         type(packet['members']) is list and len(packet['members'])==5,'EXACT_CONTROLS_PACKET_SCOPE')
    expected={'fixture_context.py','fixture_transport.py','fixture_contract.py',
              'recorder.py','check_bounded_output.py'}
    inputs={}
    pins={}
    for member in packet['members']:
        need(type(member) is dict and set(member)=={'path','bytes','sha256','body_b64'} and
             member['path'] in expected and member['path'] not in inputs and
             type(member['bytes']) is int and 0<member['bytes']<=131072,'EXACT_CONTROL_MEMBER')
        value=base64.b64decode(member['body_b64'],validate=True)
        need(len(value)==member['bytes'] and hashlib.sha256(value).hexdigest()==member['sha256'],
             'EXACT_CONTROL_MEMBER_BYTES')
        value.decode('utf-8','strict')
        inputs[member['path']]=value
        pins[member['path']]={'bytes':len(value),'sha256':member['sha256']}
    need(set(inputs)==expected,'COMPLETE_FIVE_MEMBERS')
    controls=inputs.pop('check_bounded_output.py')
    namespace={'__name__':'fixed_ndk_output_controls','__file__':'<fixed-check_bounded_output.py>'}
    exec(compile(controls,namespace['__file__'],'exec'),namespace)
    report=namespace['run_controls'](inputs)
    need(type(report) is dict and type(report.get('ok')) is bool,'EXACT_CONTROLS_RESULT')
    report['exact_packet']=dict(PACKET_PIN)
    report['five_source_members']=pins
    report['controller_Main_Android_or_namespace_actions']=0
    report['whole_invocation_resource_qualified']=False
    encoded=(json.dumps(report,sort_keys=True,indent=2)+'\n').encode()
    need(len(encoded)<=MAX_OUTPUT,'HOST_CONTROLS_REPORT_BOUND')
    count=0
    while count<len(encoded):
        amount=os.write(1,encoded[count:])
        need(amount>0,'HOST_CONTROLS_REPORT_WRITE_STALLED')
        count+=amount
    return 0 if report['ok'] else 1


if __name__=='__main__':
    raise SystemExit(main())
