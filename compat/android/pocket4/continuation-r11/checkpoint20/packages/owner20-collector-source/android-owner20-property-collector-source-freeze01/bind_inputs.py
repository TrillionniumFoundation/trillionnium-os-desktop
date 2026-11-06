"""Pure input binder for the Owner20 collector source packet.

Only an exact immutable static-build report is accepted. The output supplies a
plan fragment and one copied-artifact input. It is not a NORMAL prepare/runtime
request and does not authorize a new Main baseline or Android execution.
"""
import hashlib
import json

BUILD_BYTES = 728003
BUILD_SHA = '5cc813715a261701cad3be931b9e53145229dec7c803d828a1097e4fe4ad166b'
BUILD_SOURCE = '481f4ca861403f493e3192c8086b1b6a9c0e70312431b9d0354c664baf9ce7ba'
EXPECTED_HELPER = {
  "bytes": 22688,
  "ctime_ns": 1793945758916487566,
  "device": 66306,
  "gid": 0,
  "inode": 45664084,
  "mode": 33133,
  "mtime_ns": 1793945758910937522,
  "path": "/opt/p4-owner20-sdk-visibility-android-20261106-build-02/sdk-visibility",
  "resolved_path": "/opt/p4-owner20-sdk-visibility-android-20261106-build-02/sdk-visibility",
  "sha256": "d58b2492120aed1c96e0a0006ba9d61edd04fbc047e5faf1c13def572aba4036",
  "uid": 0
}
SOURCE_PINS = {
  "actor.py": {
    "bytes": 29821,
    "sha256": "e4edd2d14f8a699ab2bef35dd77313c06e260768414efe14d38553eddbb6c141"
  },
  "property_visibility.py": {
    "bytes": 68777,
    "sha256": "8aa61f8a7a0e79511dc3bb49e4f4f857d7dc40b68a26e431cda0af0629bf56b2"
  }
}


def need(value, message):
    if not value:
        raise RuntimeError(message)


def bind(actual_raw, source_texts):
    need(type(actual_raw) is bytes and len(actual_raw) == BUILD_BYTES and
         hashlib.sha256(actual_raw).hexdigest() == BUILD_SHA, 'EXACT_OWNER20_BUILD02_REQUIRED')
    actual = json.loads(actual_raw.decode('utf-8', 'strict'))
    need(actual['kind'] == 'p4-owner20-sdk-visibility-android-build02' and
         actual['success'] is True and actual['errors'] == [] and
         actual['source_manifest_sha256'] == BUILD_SOURCE and
         actual['Android_executable_run'] is False and actual['Android_runtime_qualified'] is False and
         actual['property_reads_or_writes'] is False and actual['namespace_or_UID_changes'] is False and
         actual['Main_or_services_changed'] is False and actual['installed_files_changed'] is False and
         actual['all_children_reaped'] is True and actual['all_inputs_unchanged'] is True,
         'STATIC_BUILD_SCOPE_OR_RESULT')
    need(actual['Android_artifact'] == EXPECTED_HELPER and
         actual['Android_artifact_before'] == actual['Android_artifact_after'] ==
             {'executable': EXPECTED_HELPER} and
         actual['Android_interpreter'] == '/system/bin/linker64' and
         actual['Android_needed'] == ['libc.so', 'libdl.so'] and
         actual['Android_actual_MD_equals_preflight'] is True and
         actual['Android_unobserved_dependencies'] == [] and
         len(actual['commands']) == 7 and all(
             row['returncode'] == 0 and row['child_reaped'] is True and
             row['first_error'] is None and row['secondary_errors'] == [] and
             row['stdout_complete'] is True and row['stderr_complete'] is True and
             row['owned_tree_cleanup_complete'] is True for row in actual['commands']),
         'EXACT_ACTUAL_ARTIFACT_OR_COMMANDS')
    need(type(source_texts) is dict and set(source_texts) == set(SOURCE_PINS), 'COLLECTOR_SOURCE_MEMBERS')
    for name, pin in SOURCE_PINS.items():
        body = source_texts[name]
        need(type(body) is bytes and len(body) == pin['bytes'] and
             hashlib.sha256(body).hexdigest() == pin['sha256'], 'COLLECTOR_SOURCE_PIN_' + name)
        compile(body, name, 'exec')  # Syntax only. Neither actor nor Capture runs.
    return {
        'schema': 1, 'scope': 'exact static inputs for one future owned generation',
        'property_visibility': {'schema': 1, 'build_result_sha256': BUILD_SHA,
            'source_manifest_sha256': BUILD_SOURCE, 'helper_bytes': EXPECTED_HELPER['bytes'],
            'helper_sha256': EXPECTED_HELPER['sha256'], 'lifetime_ms': 2000,
            'root_warmed_cache': True, 'actual_LMKD_capability_simulation': False},
        'artifact': {'role': 'sdk-visibility', 'path': EXPECTED_HELPER['path'],
            'bytes': EXPECTED_HELPER['bytes'], 'sha256': EXPECTED_HELPER['sha256'],
            'destination': 'bin/sdk-visibility', 'actual_build_metadata': EXPECTED_HELPER},
        'source_pins': SOURCE_PINS, 'new_normal_prepare_or_runtime_request_created': False,
        'Main_baseline_rebound': False, 'Android_run_authorized': False,
        'required_followup': 'Root-reviewed fresh plan, current Main fence and actual prepared binding'
    }


if __name__ == '__main__':
    print(json.dumps({'schema': 1, 'mode': 'PURE_BINDER_ONLY', 'runtime_authorized': False}))
