#!/usr/bin/env python3
"""Sign the verified release08 artifact with the current Camera2 signing identity.

This step does not install an APK, open a camera, or change Android state.
Signing key files remain local and are used only as apksigner selectors.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CERT = 'a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc'
PREVIOUS = Path('/home/alex/work/pocket4-camera-source-20261104/camera-hotplug-candidate-03/apk-release-07/result.json')
PREVIOUS_SHA = '6da344e2624fcc728e046a13c92cdb9b4e999f3808ea4844fb948e821fecc90c'

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def require(v, message):
    if not v:
        raise RuntimeError(message)

def main():
    # The exact historical receipt is supplied with the reviewed build request.
    require(sha(PREVIOUS) == PREVIOUS_SHA, 'Historical signing receipt changed')
    old = json.loads(PREVIOUS.read_bytes())
    compile_result = json.loads((ROOT/'unsigned-build-01/result.json').read_bytes())
    require(compile_result['success'] and compile_result['source_inputs_postcheck_passed'], 'Unsigned build did not qualify')
    unsigned = ROOT/'unsigned-build-01/Camera2-aligned-unsigned.apk'
    require(sha(unsigned) == compile_result['unsigned_apk']['sha256'], 'Unsigned artifact changed')
    out = ROOT/'signed-build-01'
    out.mkdir(mode=0o700, exist_ok=False)
    target = out/'Camera2-pocket4-checked-disconnect.apk'
    commands = {c['label']: c['argv'] for c in old['commands']}
    sign = list(commands['sign'])
    require(sign[:2] == ['/usr/bin/apksigner','sign'], 'Unexpected signer')
    require('--ks-pass' not in sign and '--key-pass' not in sign, 'Unexpected password-bearing signing shape')
    require(sign[sign.index('--min-sdk-version')+1] == '37', 'Signing API differs')
    sign[sign.index('--out')+1] = str(target)
    sign[-1] = str(unsigned)
    env = os.environ.copy()
    env['JAVA_TOOL_OPTIONS'] = '-Xmx256m -XX:ActiveProcessorCount=1 -XX:+UseSerialGC'
    results=[]
    def run(label, argv, timeout=90):
        start=time.monotonic()
        p=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,env=env)
        (out/(label+'.stdout')).write_bytes(p.stdout)
        (out/(label+'.stderr')).write_bytes(p.stderr)
        results.append({'label':label,'returncode':p.returncode,'elapsed_seconds':time.monotonic()-start,'executable_sha256':sha(argv[0])})
        require(p.returncode==0, label+' failed; logs retained locally')
        return p.stdout.decode('utf-8','replace')
    run('sign',sign)
    verify=list(commands['signature-verify']);verify[-1]=str(target)
    verification=run('signature-verify',verify)
    require('Signer #1 certificate SHA-256 digest: '+CERT in verification,'Certificate differs from current installed release07')
    require('Verified using v3 scheme (APK Signature Scheme v3): true' in verification,'APK v3 signature not verified')
    alignment=list(commands['alignment-verify']);alignment[-1]=str(target)
    run('alignment-verify',alignment)
    def signature_entry(n):
        return n.upper()=='META-INF/MANIFEST.MF' or re.fullmatch(r'META-INF/[^/]+\.(SF|RSA|DSA|EC)',n,re.I) is not None
    with zipfile.ZipFile(unsigned) as a,zipfile.ZipFile(target) as b:
        require(b.testzip() is None and len(b.namelist())==len(set(b.namelist())),'Signed ZIP invalid')
        first={n for n in a.namelist() if not signature_entry(n)}
        second={n for n in b.namelist() if not signature_entry(n)}
        require(first==second,'Signing changed payload inventory')
        require(all(a.read(n)==b.read(n) for n in first),'Signing changed executable or resource payload')
    require(sha(unsigned)==compile_result['unsigned_apk']['sha256'],'Unsigned artifact changed during signing')
    result={'success':True,'apk_name':target.name,'apk_sha256':sha(target),'apk_bytes':target.stat().st_size,'unsigned_sha256':sha(unsigned),'source_sha256':compile_result['source_sha256'],'certificate_sha256':CERT,'signature_v3_verified':True,'alignment_16k_verified':True,'payload_byte_preserved':True,'commands':results,'installed':False,'production_ready':False,'new_release_signing_identity_created':False}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    main()
