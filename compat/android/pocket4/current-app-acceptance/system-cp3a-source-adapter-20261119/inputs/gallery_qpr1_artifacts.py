"""Normal read-only host input gate for the selected QPR1 Gallery port.

The former install18 provenance adapter depended on retired June build outputs.
This adapter admits the current official payload and complete 2144-class build,
binds the actual signed APK to its SDK37 cryptographic verification, and exposes
the same host_evidence / payload_exact interfaces to the existing controller.
It never loads keys, invokes signing tools, starts Main, or qualifies runtime ART.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import types
import zipfile

CONTRACT_REF = {'path': '/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/inputs/host-artifact-contract.json', 'bytes': 3978, 'sha256': 'c6fb3ad1c2ec673bab72ba3808418f140d0b73051627acdf6cccac34704beb2a'}
PACKAGE = 'com.android.gallery3d'
OLD_SHA = '835fe119745324276457b4434fc39f25b633e752c822d2fc9be40eb4b2d45439'
OLD_BYTES = 7390425
NEW_SHA = '6677d382076f10f0502c813c7614c32127ccf3cd8f02756b75a8c3574980e87e'
NEW_BYTES = 7493022
DEX_SHA = '6a994fabd3494dcbf071d727922351f72ff8fdbee0d3d3c1a46b6ed30ca034ee'
DEX_BYTES = 1886696
MANIFEST_SHA = '2d4399372058787b9a9986a797ddc8f2d3722e4cee85a055721da4dc546890ee'
CERT = 'a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc'
CLASS_COUNT = 2144
MODIFIED_METHODS = [
    ['com/android/gallery3d/exif/ExifInterface.smali', 'public rewriteExif(Ljava/lang/String;Ljava/util/Collection;)Z'],
    ['com/android/gallery3d/ui/MenuExecutor$MediaOperation.smali',
     'public run(Lcom/android/gallery3d/util/ThreadPool$JobContext;)Ljava/lang/Void;'],
]
META = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')


def need(value, reason):
    if not value:
        raise RuntimeError('QPR1_GALLERY:' + reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def meta(s):
    return {k: getattr(s, k) for k in META}


def read_host(reference, maximum=2 * 1024 * 1024):
    need(type(reference) is dict and set(reference) == {'path', 'bytes', 'sha256'}, 'EXACT_PUBLIC_INPUT_REFERENCE')
    path = Path(reference['path'])
    need(path.is_absolute() and path.resolve() == path and 0 <= reference['bytes'] <= maximum,
         'BOUNDED_CANONICAL_PUBLIC_INPUT')
    need(not any(x in str(path).lower() for x in ('private-signing', 'password.txt', '.p12', '.pk8', '/data.img')),
         'NO_PRIVATE_SIGNING_OR_ACCOUNT_INPUT')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size == reference['bytes'],
             'REGULAR_SINGLE_LINK_PUBLIC_INPUT')
        raw = bytearray()
        while len(raw) < before.st_size:
            part = os.read(fd, min(65536, before.st_size - len(raw)))
            need(bool(part), 'SHORT_PUBLIC_INPUT_READ'); raw.extend(part)
        need(os.read(fd, 1) == b'' and sha(raw) == reference['sha256']
             and meta(before) == meta(os.fstat(fd)) == meta(path.lstat()), 'PUBLIC_INPUT_CHANGED')
        return bytes(raw)
    finally:
        os.close(fd)


def read_contract():
    value = json.loads(read_host(CONTRACT_REF, 65536))
    need(value['schema'] == 'QPR1-Gallery-executable-host-artifact-contract-v1'
         and value['package'] == PACKAGE and value['class_count'] == CLASS_COUNT
         and value['current_candidate']['sha256'] == NEW_SHA and value['current_candidate']['bytes'] == NEW_BYTES
         and value['official_APK_sha256'] == OLD_SHA and value['manifest_binary_sha256'] == MANIFEST_SHA
         and value['certificate_sha256'] == CERT
         and value['historical_runtime_credit_transferred'] is False,
         'EXACT_CURRENT_COHORT_CONTRACT')
    need(set(value['documents']) == {'build', 'signature', 'payload', 'descriptors', 'framework', 'publication',
                                     'factory', 'movie'},
         'COMPLETE_CURRENT_HOST_INPUT_SET')
    return value


def load_axml(contract):
    ref = contract['axml_parser']; raw = read_host(ref, 65536)
    module = types.ModuleType('gallery_actual_bound_axml'); module.__file__ = ref['path']
    exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    return module


def signature_entry(name):
    upper = name.upper()
    return upper.startswith('META-INF/') and (upper.endswith(('.SF', '.RSA', '.DSA', '.EC'))
                                             or upper == 'META-INF/MANIFEST.MF')


def admit_documents(contract, documents):
    build = documents['build']; signed = documents['signature']; payload = documents['payload']
    names = documents['descriptors']; publication = documents['publication']; framework = documents['framework']
    factory = documents['factory']; movie = documents['movie']
    need(build['schema'] == 'QPR1-Gallery-actual-DEX-rebuild-v1'
         and build['official_APK_sha256'] == OLD_SHA and build['new_DEX_sha256'] == DEX_SHA
         and build['new_DEX_bytes'] == DEX_BYTES and build['all_class_IR_checked'] == CLASS_COUNT
         and build['target_classes'] == 2 and build['non_target_classes_unchanged'] == CLASS_COUNT - 2
         and build['only_changed_APK_payload'] == ['classes.dex']
         and build['manifest_resources_and_other_payload_bytes_unchanged'] is True
         and build['alignment_16KiB_verified'] is True and build['official_image_unchanged'] is True,
         'COMPLETE_ACTUAL_QPR1_TWO_METHOD_BUILD_REQUIRED')
    rows = build['classes']
    need(len(rows) == CLASS_COUNT and len({r['class'] for r in rows}) == CLASS_COUNT
         and all(r['equal_expected'] is True for r in rows)
         and sum(r['target'] is True for r in rows) == 2
         and {r['class'] for r in rows if r['target']} == {r[0] for r in MODIFIED_METHODS},
         'ALL_2144_CLASS_IR_IDENTITIES_REQUIRED')
    need(type(names) is list and len(names) == len(set(names)) == CLASS_COUNT
         and names == sorted('L' + r['class'][:-6] + ';' for r in rows), 'ACTUAL_CURRENT_DEX_CLASS_SET_REQUIRED')
    need([[r['class'], r['replaced_method']] for r in build['method_port']] == MODIFIED_METHODS
         and all(r['entire_QPR1_target_preimage_byte_equal_to_reviewed_preimage'] is True
                 and r['non_target_method_bytes_preserved'] is True for r in build['method_port']),
         'EXACT_REVIEWED_METHOD_PORT_WITH_ALL_OTHER_METHODS_PRESERVED')
    need(signed['schema'] == 'QPR1-existing-key-app-signature-custody-v1'
         and signed['certificate_DER_sha256'] == CERT and signed['existing_key_metadata_unchanged'] is True
         and signed['new_key_generated'] is False and signed['key_contents_returned_or_logged'] is False
         and len(signed['apps']) == 1, 'EXISTING_LEGAL_SIGNER_CUSTODY_REQUIRED')
    app = signed['apps'][0]; identity = app['signed_identity']
    need(app['package'] == PACKAGE and app['all_non_signature_ZIP_members_unchanged'] is True
         and app['v2_and_v3_existing_signer_verified'] is True and app['alignment_16KiB_verified'] is True
         and identity['package'] == PACKAGE and identity['version_code'] == 40030
         and identity['split_name'] is None and identity['bytes'] == NEW_BYTES and identity['sha256'] == NEW_SHA
         and identity['metadata_outputs_bound_to_apk_sha256'] == NEW_SHA
         and identity['signature_verified'] is True and identity['verification_SDK_range'] == [37, 37]
         and identity['signer_certificate_sha256'] == [CERT]
         and identity['selected_verified_signing_scheme'] == {'scheme': 'v3', 'certificate_sha256': [CERT]},
         'ACTUAL_SDK37_SIGNATURE_AND_BODY_IDENTITY_REQUIRED')
    need(payload['schema'] == 'QPR1-Gallery-official-payload-binding-v1'
         and payload['official_APK']['sha256'] == OLD_SHA and payload['official_APK']['bytes'] == OLD_BYTES
         and payload['candidate_APK'] == contract['current_candidate']
         and payload['candidate_DEX']['sha256'] == DEX_SHA and payload['candidate_DEX']['bytes'] == DEX_BYTES
         and payload['manifest_binary_sha256'] == MANIFEST_SHA and payload['class_count'] == CLASS_COUNT
         and payload['only_changed_payload'] == ['classes.dex']
         and payload['candidate_public_signing_block'] == identity['public_signing_block']
         and payload['official_public_signing_block']['certificate_sha256'] == [CERT],
         'OFFICIAL_BASE_AND_SIGNED_PORT_SAME_CONTENT_BINDING')
    need(publication['schema'] == 'QPR1-Gallery-host-input-publication-v1'
         and publication['official_image_full_sha256_verified'] == contract['official_image_sha256']
         and publication['official_image_identity_before'] == publication['official_image_identity_after']
         and publication['candidate'] == contract['current_candidate']
         and publication['current_build_proof'] == contract['documents']['build']
         and publication['current_signature_proof'] == contract['documents']['signature']
         and publication['temporary_extracted_APK_and_JAR_files_removed'] is True,
         'EXACT_ACTUAL_IMAGE_EXTRACTION_CUSTODY')
    need(framework['schema'] == 'QPR1-Gallery-framework-host-inputs-v1'
         and framework['official_image_sha256'] == contract['official_image_sha256']
         and len(framework['files']) == 6 and len({r['guest_path'] for r in framework['files']}) == 6,
         'QPR1_FRAMEWORK_AND_FOUR_SHARED_LIBRARY_INPUTS')
    need(factory['schema'] == 'QPR1-Gallery-actual-application-factory-v1'
         and factory['actual_APK_sha256'] == NEW_SHA and factory['actual_DEX_sha256'] == DEX_SHA
         and factory['manifest_binary_sha256'] == MANIFEST_SHA
         and factory['factory'] == 'androidx.core.app.CoreComponentFactory'
         and factory['superclass'] == 'Landroid/app/AppComponentFactory;'
         and factory['instantiateClassLoader_override_absent'] is True,
         'CURRENT_DEX_AND_MANIFEST_CLASSLOADER_FACTORY_CONTRACT')
    need(movie['schema'] == 'QPR1-Gallery-current-movie-source-v1'
         and movie['state'] == 'QPR1_MOVIE_CODE_SOURCE_INSPECTED_NOT_INSTALLED'
         and movie['official_APK_sha256'] == OLD_SHA and movie['candidate_APK_sha256'] == NEW_SHA
         and movie['all_movie_classes_unchanged_by_current_port'] is True
         and movie['modified_methods'] == MODIFIED_METHODS and movie['movie_classes']
         and movie['runtime_credit'] == 0, 'CURRENT_MOVIE_SOURCE_NO_HISTORICAL_RUNTIME_CREDIT')
    return identity


def admit_candidate_bytes(raw, payload, axml):
    need(len(raw) == NEW_BYTES and sha(raw) == NEW_SHA, 'ACTUAL_WHOLE_SIGNED_APK_BYTES')
    expected = {r['name']: r for r in payload['candidate_payloads']}
    original = {r['name']: r for r in payload['official_payloads']}
    need(len(expected) == len(payload['candidate_payloads']) and len(original) == len(payload['official_payloads'])
         and set(expected) == set(original), 'EXACT_NON_DUPLICATE_OFFICIAL_PAYLOAD_SET')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        need(len(names) == len(set(names)) and archive.testzip() is None, 'ACTUAL_APK_ZIP_INTEGRITY')
        actual_names = {n for n in names if not signature_entry(n)}
        need(actual_names == set(expected), 'ACTUAL_APK_MEMBER_SET')
        changed = []
        for name in sorted(actual_names):
            body = archive.read(name)
            record = {'name': name, 'bytes': len(body), 'sha256': sha(body)}
            need(record == expected[name], 'ACTUAL_APK_MEMBER_CHANGED:' + name)
            if record != original[name]: changed.append(name)
        need(changed == ['classes.dex'], 'ONLY_CURRENT_REVIEWED_DEX_CHANGED')
        manifest = archive.read('AndroidManifest.xml'); metadata = axml.metadata(manifest)
        need(sha(manifest) == MANIFEST_SHA and metadata['package'] == PACKAGE
             and metadata['version_code'] == 40030 and metadata['split_name'] is None
             and metadata['version_name'] == '1.1.40030', 'ACTUAL_MANIFEST_IDENTITY')
        dex = archive.read('classes.dex')
        need(len(dex) == DEX_BYTES and sha(dex) == DEX_SHA, 'ACTUAL_QPR1_DEX_BYTES')
        need(not any(n.startswith('lib/') or n.endswith('.so') for n in names), 'EMPTY_APK_NATIVE_NAMESPACE_PRESERVED')
    return {'non_signature_entries': len(expected), 'changed_entries': changed,
            'manifest_sha256': MANIFEST_SHA, 'dex_sha256': DEX_SHA,
            'native_payloads': {}, 'same_native_payloads': True,
            'official_QPR1_APK_sha256': OLD_SHA, 'candidate_APK_sha256': NEW_SHA}


def host_evidence():
    contract = read_contract()
    raw = {name: read_host(ref) for name, ref in contract['documents'].items()}
    documents = {name: json.loads(body) for name, body in raw.items()}
    identity = admit_documents(contract, documents)
    axml = load_axml(contract); candidate = contract['current_candidate']; path = Path(candidate['path'])
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size == NEW_BYTES,
             'REGULAR_CURRENT_SIGNED_APK')
        body = os.pread(fd, NEW_BYTES + 1, 0)
        payload = admit_candidate_bytes(body, documents['payload'], axml)
        block = axml.signing_block_certificates('/proc/self/fd/' + str(fd))
        need(block == identity['public_signing_block']
             and all(block['certificate_sha256_by_scheme'][k] == [CERT] for k in ('0x7109871a', '0xf05368c0')),
             'SAME_DESCRIPTOR_RAW_V2_V3_SIGNATURE_BLOCK')
        need(meta(before) == meta(os.fstat(fd)) == meta(path.lstat())
             and sha(os.pread(fd, NEW_BYTES + 1, 0)) == NEW_SHA, 'SIGNED_APK_CHANGED_DURING_HOST_PROOF')
    finally:
        os.close(fd)
    need(all(read_host(contract['documents'][name]) == value for name, value in raw.items()), 'HOST_PROOF_INPUT_CHANGED')
    return {'schema': 'QPR1-Gallery-current-host-artifacts-verified-v1', 'contract': CONTRACT_REF,
            'input_hashes': {contract['documents'][name]['path']: sha(value) for name, value in raw.items()},
            'candidate_apk_sha256': NEW_SHA, 'official_apk_sha256': OLD_SHA,
            'same_certificate': CERT, 'actual_QPR1_class_IR_verified': CLASS_COUNT,
            'actual_SDK37_signature_verified': True, 'payload_scope': payload,
            'private_signing_key_read': False, 'historical_runtime_credit_transferred': False,
            'runtime_ART_qualified': False, 'new_signature_or_Java_processes': 0}


def payload_exact(held, identity):
    contract = read_contract(); payload = json.loads(read_host(contract['documents']['payload']))
    held.verify(); raw = os.pread(held.fd, NEW_BYTES + 1, 0)
    result = admit_candidate_bytes(raw, payload, load_axml(contract))
    need(identity.native_payload(raw) == {}, 'ACTUAL_IDENTITY_NATIVE_PAYLOAD_PARSER_AGREEMENT')
    held.verify()
    return result
