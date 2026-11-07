"""Exact install-only wrapper. All authority is frozen into one packet.
This template is not executable admission before actual entry-control binding.
Root is the sole dispatcher. No existing package/UID or runtime is adopted.
"""
import base64
import hashlib
import json
import os
import re
import sys
import types

PACKET_BYTES = __PACKET_BYTES__
PACKET_SHA256 = '__PACKET_SHA256__'
PACKET_B64 = '__PACKET_B64__'
SOURCE_MANIFEST = {'bytes':1054,'sha256':'684209fb84cf81921a1c65e8c52c7bf95db87ca0167d46badf8a8d974a2ba237'}
WORKER = {'bytes':22059,'sha256':'d7ba4227604949ed80d491c6cef45e4f52267267e002b1e6ff796cdd68d1b046'}
SOURCE_NAMES = {
    'fixture_contract.py','fixture_context.py','fixture_transport.py',
    'fixture_phases.py','current_discovery.py','install_lease.py','install_worker.py',
}
SOURCE_ROOT = '/home/alex/work/pocket4-original-ndk-fixture-APK05-install-02/source'


def need(value,code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def body(row,maximum):
    need(type(row) is dict and set(row)=={'body','bytes','sha256'} and
         type(row['body']) is str and type(row['bytes']) is int and
         0<row['bytes']<=maximum and type(row['sha256']) is str and
         re.fullmatch('[0-9a-f]{64}',row['sha256']),'EXACT_WRAPPER_MEMBER_SHAPE')
    raw=row['body'].encode('utf-8')
    need(len(raw)==row['bytes'] and sha(raw)==row['sha256'],'EXACT_WRAPPER_MEMBER_HASH')
    return raw


def main():
    entered=False
    try:
        need(sys.dont_write_bytecode and sys.flags.isolated,
             'ISOLATED_NO_BYTECODE_INSTALL_WRAPPER_REQUIRED')
        need(type(PACKET_BYTES) is int and 0<PACKET_BYTES<=1048576 and
             len(PACKET_B64)<=1398104,'FIXED_INSTALL_PACKET_BOUND')
        raw=base64.b64decode(PACKET_B64,validate=True)
        need(len(raw)==PACKET_BYTES and sha(raw)==PACKET_SHA256,
             'FIXED_INSTALL_PACKET_WHOLE_HASH')
        envelope=json.loads(raw)
        need(type(envelope) is dict and set(envelope)=={'binding','packet'},
             'EXACT_INSTALL_WRAPPER_ENVELOPE')
        packet=envelope['packet']
        need(type(packet) is dict and set(packet)=={'schema','sources','manifest','references'} and
             packet['schema']==1 and set(packet['sources'])==SOURCE_NAMES,
             'EXACT_INSTALL_WRAPPER_SEVEN_SOURCES')
        manifest_raw=body(packet['manifest'],65536)
        need({'bytes':len(manifest_raw),'sha256':sha(manifest_raw)}==SOURCE_MANIFEST,
             'FROZEN_INSTALL_SOURCE_MANIFEST_CHANGED')
        manifest=json.loads(manifest_raw)
        need(set(manifest)=={'schema','files'} and
             manifest['schema']=='pocket4-original-ndk-fixture-source-v1' and
             set(manifest['files'])==SOURCE_NAMES,'EXACT_INSTALL_WRAPPER_MANIFEST')
        sources={name:body(row,131072) for name,row in packet['sources'].items()}
        need(all(manifest['files'][name]=={'bytes':len(value),'sha256':sha(value)}
                 for name,value in sources.items()),'SEVEN_INSTALL_SOURCE_PINS_CHANGED')
        worker_raw=sources['install_worker.py']
        need({'bytes':len(worker_raw),'sha256':sha(worker_raw)}==WORKER,
             'EXACT_UNBOUND_INSTALL_WORKER_REQUIRED')
        worker=types.ModuleType('fixed_original_ndk_install_worker')
        worker.__file__=SOURCE_ROOT+'/install_worker.py'
        exec(compile(worker_raw,worker.__file__,'exec'),worker.__dict__)
        need(worker.PENDING_BINDING is None,'WORKER_DEFAULT_MUST_REMAIN_UNBOUND')
        entered=True
        return worker.run_install(envelope['binding'],packet)
    except BaseException as error:
        message=str(error)
        item={'type':type(error).__name__,'errno':getattr(error,'errno',None)}
        if re.fullmatch('[A-Z][A-Z0-9_: ]{0,159}',message):
            item['code']=message
        else:
            raw=message.encode('utf-8','replace')
            item.update(message_bytes=len(raw),message_sha256=sha(raw))
        # A wrapper exception after entry cannot claim that no install occurred.
        # It never manufactures an installed UID or a completed worker result.
        result={'schema':1,'kind':'pocket4-original-ndk-install-wrapper-failure02',
            'ok':False,'error':item,'worker_entered':entered,'outcome_unknown':entered,
            'automatic_retry':False,'installed_UID':None,
            'original_NdkTests_runtime_qualified':False}
        raw=(json.dumps(result,sort_keys=True,separators=(',',':'))+'\n').encode()
        need(len(raw)<=8192,'INSTALL_WRAPPER_FAILURE_BOUND')
        sys.stdout.buffer.write(raw)
        sys.stdout.buffer.flush()
        return 1


if __name__=='__main__':
    raise SystemExit(main())
