"""Normal complete Native/ART pair completion; no signing or runtime credit.

The rules follow the actual 515-file normal producer. These pure validators
also reject JSON booleans where the compiled contract requires integers.
"""
TARGETS = ['libberberis_arm64', 'com.android.art']
LOCK_SHA = '09a020b99c5f9f1876c69450d01ac99907cd6dda97cb4f69601f70151ea43d2b'
ENGINE_FILES_SHA = '6633fee76068fa421d5cfd3fd6f3d2440b2fa8d04b92223a1b1b9e7f9eba4139'
REQUIRED_COMPILE_SOURCES = [
    'art/runtime/runtime.cc',
    'art/runtime/native_bridge_art_interface.cc',
    'art/libnativebridge/native_bridge.cc',
    'art/libnativebridge/droidloom_generation.cc',
    'frameworks/libs/binary_translation/kernel_api/proc_maps_generation.cc',
    'frameworks/libs/binary_translation/kernel_api/proc_maps_provenance.cc',
    'frameworks/libs/binary_translation/kernel_api/unistd_emulation.cc',
]
ART_PATHS = (
    'art/libnativebridge/Android.bp',
    'art/libnativebridge/droidloom_generation.cc',
    'art/libnativebridge/droidloom_generation.h',
    'art/libnativebridge/include/nativebridge/droidloom_generation_protocol.h',
    'art/libnativebridge/include/nativebridge/native_bridge.h',
    'art/libnativebridge/libnativebridge.map.txt',
    'art/libnativebridge/native_bridge.cc',
    'art/runtime/Android.bp',
    'art/runtime/native_bridge_art_interface.cc',
    'art/runtime/runtime.cc',
)
PAIR_KEYS = {'schema', 'abi', 'protocol', 'host_abi', 'engine_sha256',
             'art_apex_sha256', 'libart_sha256', 'libnativebridge_sha256', 'apex_pubkey_sha256'}


def need(value, message):
    if not value:
        raise RuntimeError(message)


def digest(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def pair_contract_shape(pair):
    need(type(pair) is dict and set(pair) == PAIR_KEYS,
         'ordinary pair compiled contract fields differ')
    need(all(type(pair[key]) is int and pair[key] == 1 for key in ('schema', 'abi'))
         and pair['protocol'] == 'DLOOMGE1-PROCMET2' and pair['host_abi'] == 'x86_64'
         and all(digest(pair[key]) for key in PAIR_KEYS if key.endswith('_sha256')),
         'ordinary pair compiled component contract differs')
    return pair


def pair_engine_marker(raw):
    marker = b'DROIDLOOM_NATIVE_GENERATION=1;ROLE=ENGINE;ABI=1;PROTOCOL=DLOOMGE1-PROCMET2;\0'
    prefix = b'DROIDLOOM_NATIVE_GENERATION='
    need(type(raw) is bytes and len(raw) >= 20 and raw[:6] == b'\x7fELF\x02\x01'
         and int.from_bytes(raw[16:18], 'little') == 3
         and int.from_bytes(raw[18:20], 'little') == 62,
         'ordinary pair engine is not an x86_64 shared ELF')
    offsets = []; position = 0
    while True:
        position = raw.find(prefix, position)
        if position < 0:
            break
        offsets.append(position)
        need(raw.startswith(marker, position), 'ordinary pair engine has a foreign or disabled marker')
        position += len(prefix)
    need(offsets, 'ordinary pair engine lacks the compiled enabled marker')
    return offsets


def validate_records(attempt, inputs, command):
    for document in (attempt, inputs, command):
        need(type(document) is dict and type(document.get('schema')) is int and document['schema'] == 1,
             'normal pair record schema differs')
        need(document.get('targets') == TARGETS and document.get('dependency_mode') == 'Strict'
             and document.get('private_AppZygote_role_authorized') is False
             and document.get('installation_performed') is False
             and document.get('runtime_qualified') is False, 'normal pair completion scope widened')
    need(attempt.get('state') == 'CLAIMED_BEFORE_SOURCE_PROJECTION'
         and attempt.get('scope') == inputs.get('scope') == 'ordinary-app-complete-engine-art-pair'
         and attempt.get('source_lock_sha256') == inputs.get('source_lock_sha256') == LOCK_SHA
         and all(type(attempt.get(key)) is int and attempt[key] == 1
                 for key in ('engine_compiled_macro', 'ART_compiled_macro'))
         and inputs.get('selected_targets') == TARGETS
         and inputs.get('frozen_engine_files_sha256') == ENGINE_FILES_SHA
         and inputs.get('required_actual_compile_sources') == REQUIRED_COMPILE_SOURCES
         and type(inputs.get('effective_engine_files')) is dict
         and len(inputs['effective_engine_files']) == 926
         and all(digest(value) for value in inputs['effective_engine_files'].values())
         and type(inputs.get('frozen_ART_inputs')) is list and len(inputs['frozen_ART_inputs']) == 10,
         'normal pair frozen compiled source record differs')
    need(command.get('state') == 'NORMAL_BUILD_SUCCEEDED_ACTUAL_PAIR_RECORDED'
         and command.get('source_projection_restored') is True,
         'normal pair command has not successfully restored its source')
    for document in (inputs, command):
        need(document.get('full_translation_unit_qualification_verified') is False
             and document.get('signature_and_payload_verification_complete') is False,
             'normal compilation cannot grant later artifact qualification')
    return pair_contract_shape(command.get('compiled_engine_ART_pair'))
