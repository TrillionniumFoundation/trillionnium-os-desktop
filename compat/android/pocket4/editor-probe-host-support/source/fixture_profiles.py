"""Exact original Editor03/Probe03 inputs, no historical runtime authority."""
PROBE = {'package': 'local.pocket4.fixture', 'uid': 10115, 'version_code': 0,
    'component': 'local.pocket4.fixture/.ProbeActivity',
    'apks': [{'bytes': 12713, 'sha256': '91e352c25e7c6ef54aa53ce652931e40ad1437dfcd0ebad2529bc662558a3dd6'}],
    'certificate_sha256': None, 'require_v3': False}
EDITOR = {'package': 'org.droidloom.qa.editorcontract', 'uid': 10149, 'version_code': 1,
    'component': 'org.droidloom.qa.editorcontract/.EditorContractActivity',
    'apks': [{'bytes': 20883, 'sha256': '0d08f59024e4228e5d5b8f56742aafd1fbc04966d74224acd48542e09482743d'}],
    'certificate_sha256': None, 'require_v3': False}
NATIVE_HELPER = {'package': 'local.pocket4.actions.v2', 'uid': 10125, 'version_code': 2,
    'component': None, 'apks': [{'bytes': 20847, 'sha256': 'a5368465d5f6faef3299bf1ba6d6bde268cc8b37c72401c6e668872b24725058'}],
    'certificate_sha256': None, 'require_v3': False}
TASK_PROOF = {'path': '/home/alex/work/pocket4-editor-ui-tools-20261105-r12-03/task-option-proof.json',
    'bytes': 17797, 'sha256': '9cb008b7050d3bb0b8da2221140c02b39ebde973833b5ee24039932e266e90a5'}
LIMITS = {
    'qa_probe03': {'business_seconds': 240, 'cleanup_seconds': 35, 'maximum_UI_actions': 14,
        'maximum_native_launches': 2, 'native_launch_timeout': 45, 'maximum_owned_nonce_routes': 0,
        'permission_writes': 0, 'account_operations': 0, 'package_mutations': 0},
    'editor_ui03': {'business_seconds': 360, 'cleanup_seconds': 45, 'maximum_UI_actions': 20,
        'maximum_native_launches': 2, 'native_launch_timeout': 45, 'maximum_owned_nonce_routes': 2,
        'permission_writes': 0, 'account_operations': 0, 'package_mutations': 0},
}

def profiles(kind):
    if kind not in LIMITS:
        raise RuntimeError('ONLY_ORIGINAL_QA03_AND_EDITOR03_SCOPES')
    return (PROBE if kind == 'qa_probe03' else EDITOR), NATIVE_HELPER, LIMITS[kind]
