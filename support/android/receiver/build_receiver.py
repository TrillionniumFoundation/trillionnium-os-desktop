#!/usr/bin/env python3
"""Build the exact original helper/instrumentation increment without installing.

Default mode only writes reviewable generated sources and a provenance record.
Compilation and signing are explicit, bounded steps. No install/start commands,
new package, signing key creation, or private key/password read is implemented.
"""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import zipfile


ROOT = Path(__file__).resolve().parent
PREIMAGES = {
    'android_app.py': '8c9856a3791f0a208e59b00137547466c9f84d3a60d7a2cae700980de43f677b',
    'ActionRunner.java': 'bf3a577bfbb9b0f4b9c6035c0423e73f8fef0e1df34dd7dea2140efbe6308570',
}
ORIGINAL_APK_SHA256 = 'a5368465d5f6faef3299bf1ba6d6bde268cc8b37c72401c6e668872b24725058'
ANDROID_JAR_SHA256 = '4566663c3876e022b4fa4ced8c8697c4ab1688267f090114fd92d027b32e619b'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('reviewed upstream patch context changed')
    return text.replace(old, new, 1)


def sources(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    for name, expected in PREIMAGES.items():
        if sha(ROOT / 'upstream' / name) != expected:
            raise ValueError('upstream source pin mismatch: ' + name)
    helper = (ROOT / 'upstream/android_app.py').read_text()
    extension = (ROOT / 'organ_extension.py').read_text()
    helper = replace_once(helper, 'def dispatch(r):\n', extension + '\n\ndef dispatch(r):\n'
                          "    if r.get('op') in ('organ-observe','organ-set-text','organ-readback'):return _organ_dispatch(r)\n")
    helper = replace_once(helper, 'try:r=json.loads(raw)',
                          'try:r=json.loads(raw,object_pairs_hook=_organ_pairs,parse_constant=_organ_nonfinite)')
    (output / 'android-digitalis-observe-helper').write_text(helper)
    runner = (ROOT / 'upstream/ActionRunner.java').read_text()
    runner = replace_once(runner, '  private boolean actionAttempted;',
                          '  private boolean actionAttempted;\n  private OrganBinding organ;')
    runner = replace_once(runner,
        '      JSONObject r=new JSONObject(new String(Base64.decode(encoded,Base64.DEFAULT),StandardCharsets.UTF_8));',
        '      JSONObject r=new JSONObject(new String(Base64.decode(encoded,Base64.DEFAULT),StandardCharsets.UTF_8));\n'
        '      organ=OrganBinding.parse(r);')
    runner = replace_once(runner, '    if(op.equals("find")){JSONArray a=new JSONArray();',
        '    if(op.equals("find")&&organ!=null)return organ.read(ui,selected,found,!truncated&&nullChildren==0);\n'
        '    if(op.equals("find")){JSONArray a=new JSONArray();')
    runner = replace_once(runner,
        '    actionAttempted=true;require(n.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,b),"SET_TEXT_REJECTED");boolean verified=false;',
        '    if(organ!=null)organ.beforeAction(ui,selected,n);\n'
        '    actionAttempted=true;require(n.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,b),"SET_TEXT_REJECTED");boolean verified=false;')
    runner = replace_once(runner,
        '    return new JSONObject().put("ok",true).put("performed",op).put("characters",value.codePointCount(0,value.length()))\n'
        '      .put("readback_verified",verified).put("password",n.isPassword());',
        '    JSONObject completed=new JSONObject().put("ok",true).put("performed",op).put("characters",value.codePointCount(0,value.length()))\n'
        '      .put("readback_verified",verified).put("password",n.isPassword());\n'
        '    return organ==null?completed:organ.completed(completed);')
    runner = replace_once(runner,
        '      result.put("ok",false).put("error",message).put("automatic_retry",false).put("outcome_unknown",actionAttempted);',
        '      result.put("ok",false).put("error",message).put("automatic_retry",false).put("outcome_unknown",actionAttempted);\n'
        '      if(organ!=null)organ.decorate(result);')
    source = output / 'src/local/pocket4/actions/v2'
    source.mkdir(parents=True)
    (source / 'ActionRunner.java').write_text(runner)
    for path in sorted((ROOT / 'runner').glob('*.java')):
        shutil.copyfile(path, source / path.name)
    record = {
        'schema_version': 1, 'scope': 'generated sources only; no deployment or Android qualification',
        'package': 'local.pocket4.actions.v2', 'original_source_sha256': PREIMAGES,
        'source_sha256': {str(p.relative_to(output)): sha(p) for p in sorted(output.rglob('*')) if p.is_file()},
    }
    (output / 'build-record.json').write_text(json.dumps(record, indent=2) + '\n')
    return output, record


def run(argv, timeout=120):
    # No shell expansion and no credentials echoed into build logs.
    result = subprocess.run([str(value) for value in argv], capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(Path(str(argv[0])).name + ' failed: ' + result.stderr.decode('utf-8', 'replace')[-4000:])
    return result.stdout.decode('utf-8', 'replace')


def certificates(apksigner, apk):
    import re
    output = run([apksigner, 'verify', '--verbose', '--print-certs', apk])
    fingerprints = re.findall(r'^Signer #\d+ certificate SHA-256 digest: ([0-9a-fA-F]{64})$', output, re.M)
    if not fingerprints:
        raise ValueError('APK has no verified signer identity')
    return sorted(value.lower() for value in fingerprints)


def signing_block_present(path):
    """Recognize an APK v2/v3 signing block adjacent to the central directory."""
    raw = Path(path).read_bytes()
    end = raw.rfind(b'PK\x05\x06', max(0, len(raw) - 65557))
    if end < 0 or end + 22 > len(raw):
        raise ValueError('invalid original APK ZIP directory')
    comment = struct.unpack_from('<H', raw, end + 20)[0]
    if end + 22 + comment != len(raw):
        raise ValueError('invalid original APK ZIP trailer')
    directory = struct.unpack_from('<I', raw, end + 16)[0]
    if directory < 24 or raw[directory - 16:directory] != b'APK Sig Block 42':
        return False
    length = struct.unpack_from('<Q', raw, directory - 24)[0]
    start = directory - length - 8
    if start < 0 or struct.unpack_from('<Q', raw, start)[0] != length:
        raise ValueError('invalid original APK signing block')
    return True


def v1_signature(name):
    upper = name.upper()
    if not upper.startswith('META-INF/'):
        return False
    leaf = upper[len('META-INF/'):]
    return leaf == 'MANIFEST.MF' or ('/' not in leaf and leaf.endswith(('.SF', '.RSA', '.DSA', '.EC')))


def repack_original_apk(original_apk, dex_file, output_apk):
    """Preserve verified binary manifest/resources, replace dex, remove signing.

    Rewriting ZIP removes the non-ZIP APK Signing Block. Resource contents are
    compared byte-for-byte after writing. The original XML is never invented.
    """
    if sha(original_apk) != ORIGINAL_APK_SHA256:
        raise ValueError('original APK pin mismatch')
    replacement = Path(dex_file).read_bytes()
    if not replacement.startswith(b'dex\n') or not 0 < len(replacement) <= 4 * 1024 * 1024:
        raise ValueError('invalid replacement dex bound or magic')
    preserved, removed = {}, []
    original_block = signing_block_present(original_apk)
    with zipfile.ZipFile(original_apk) as original:
        entries = original.infolist()
        names = [entry.filename for entry in entries]
        if len(names) != len(set(names)) or names.count('classes.dex') != 1 or names.count('AndroidManifest.xml') != 1:
            raise ValueError('original APK entries are ambiguous')
        if any(name.startswith('classes') and name.endswith('.dex') and name != 'classes.dex' for name in names):
            raise ValueError('original multidex package is outside this reviewed profile')
        manifest = original.read('AndroidManifest.xml')
        if not manifest.startswith(b'\x03\x00\x08\x00'):
            raise ValueError('original binary Android manifest missing')
        with zipfile.ZipFile(output_apk, 'x') as output:
            for entry in entries:
                if v1_signature(entry.filename):
                    removed.append(entry.filename)
                    continue
                raw = replacement if entry.filename == 'classes.dex' else original.read(entry)
                if entry.filename != 'classes.dex':
                    preserved[entry.filename] = hashlib.sha256(raw).hexdigest()
                output.writestr(copy.copy(entry), raw)
    with zipfile.ZipFile(output_apk) as written:
        if any(v1_signature(name) for name in written.namelist()) or signing_block_present(output_apk):
            raise ValueError('old signing material survived APK rewrite')
        if written.read('classes.dex') != replacement:
            raise ValueError('replacement dex changed during APK rewrite')
        for name, digest in preserved.items():
            if hashlib.sha256(written.read(name)).hexdigest() != digest:
                raise ValueError('original APK resource changed during rewrite')
    return {'resource_source': 'verified original APK; no reconstructed manifest XML',
            'original_binary_manifest_sha256': hashlib.sha256(manifest).hexdigest(),
            'preserved_entry_sha256': preserved, 'replacement_classes_dex_sha256': hashlib.sha256(replacement).hexdigest(),
            'removed_v1_signature_entries': removed, 'removed_apk_signing_block': original_block,
            'old_signatures_retained': False}


def compile_sources(output, record, sdk, manifest, original_apk, keystore=None, password_env=None,
                    *, reuse_original_resources=False):
    sdk, original_apk = Path(sdk).resolve(), Path(original_apk).resolve()
    android = sdk / 'platforms/android-35/android.jar'
    build_tools = sdk / 'build-tools/35.0.1'
    if sha(android) != ANDROID_JAR_SHA256 or sha(original_apk) != ORIGINAL_APK_SHA256:
        raise ValueError('original Android SDK/APK pin mismatch')
    if not reuse_original_resources:
        manifest = Path(manifest).resolve()
        if sha(manifest) != 'f5b4edf0f7364414b46339be4ce4c6d8f5c5c86cd3f1035620ce4aeb467f4a10':
            raise ValueError('original manifest pin mismatch')
    original_certs = certificates(build_tools / 'apksigner', original_apk)
    classes, dex = output / 'classes', output / 'dex'
    classes.mkdir()
    dex.mkdir()
    run(['/usr/bin/javac', '-encoding', 'UTF-8', '-source', '8', '-target', '8', '-bootclasspath',
         android, '-d', classes, *sorted((output / 'src').rglob('*.java'))])
    run([sdk / 'cmdline-tools/latest/bin/d8', '--min-api', '26', '--lib', android, '--output', dex,
         *sorted(classes.rglob('*.class'))])
    if reuse_original_resources:
        record['original_resource_preservation'] = repack_original_apk(original_apk, dex / 'classes.dex', output / 'raw.apk')
    else:
        run([build_tools / 'aapt', 'package', '-f', '-M', manifest, '-I', android, '-F', output / 'raw.apk'])
        run(['/usr/bin/zip', '-j', '-q', output / 'raw.apk', dex / 'classes.dex'])
    run([build_tools / 'zipalign', '-f', '4', output / 'raw.apk', output / 'aligned.apk'])
    unsigned = subprocess.run([str(build_tools / 'apksigner'), 'verify', str(output / 'aligned.apk')],
                              capture_output=True, timeout=120)
    if unsigned.returncode == 0:
        raise ValueError('unsigned candidate unexpectedly carries a valid APK signature')
    record.update(scope='compiled original-package candidate; no deployment or Android qualification',
                  compile_sdk=35, android_jar_sha256=sha(android), original_apk_sha256=sha(original_apk),
                  original_signer_sha256=original_certs, unsigned_apk_sha256=sha(output / 'aligned.apk'),
                  unsigned_apk_signature_valid=False, signing_required_for_deployment=True)
    if keystore is not None:
        import re
        if not password_env or not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*', password_env):
            raise ValueError('explicit original signing password environment variable required')
        # apksigner consumes the original environment variable directly. This
        # script never reads its value or creates/substitutes signing material.
        run([build_tools / 'apksigner', 'sign', '--ks', Path(keystore).resolve(), '--ks-pass',
             'env:' + password_env, '--out', output / 'actions-v2.apk', output / 'aligned.apk'])
        candidate_certs = certificates(build_tools / 'apksigner', output / 'actions-v2.apk')
        if candidate_certs != original_certs:
            (output / 'actions-v2.apk').unlink()
            raise ValueError('candidate signer differs from original; candidate removed')
        record.update(candidate_signer_sha256=candidate_certs, signer_identity_matches_original=True,
                      candidate_apk_sha256=sha(output / 'actions-v2.apk'), signing_required_for_deployment=False)
    (output / 'build-record.json').write_text(json.dumps(record, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--compile', action='store_true')
    parser.add_argument('--sdk', default='/opt/android-sdk')
    parser.add_argument('--manifest')
    parser.add_argument('--reuse-original-resources', action='store_true',
                        help='preserve binary manifest/resources from the verified original APK; no XML reconstruction')
    parser.add_argument('--original-apk', default='/opt/pocket4-android-controls/actions-v2.apk')
    parser.add_argument('--original-keystore')
    parser.add_argument('--password-env')
    args = parser.parse_args()
    if args.compile and bool(args.manifest) == args.reuse_original_resources:
        parser.error('--compile requires exactly one of --manifest or --reuse-original-resources')
    if args.original_keystore and not args.compile:
        parser.error('signing requires --compile')
    output, record = sources(args.output)
    if args.compile:
        compile_sources(output, record, args.sdk, args.manifest, args.original_apk,
                        args.original_keystore, args.password_env,
                        reuse_original_resources=args.reuse_original_resources)
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
