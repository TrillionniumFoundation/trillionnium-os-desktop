"""Use the actual r9 adapter's R5 Session without overriding any method.

The frozen r9 source declares R5; actual build proof remains required. Its source and recorder bindings must match;
no old R3 global is changed and no legacy constructor shim is reused.
"""
R5_MANIFEST = '6d99374e1580083fd0f30b7f9b3c520306680760c97ad0d5400798fda427fb6e'
QA_MANIFEST = '4eb11cf497615272c1bef280bbd849de4f983ba4147ea9356356dff076ce9c56'
SELF = 'org.droidloom.qa.bili.r9'


def new_session(adapter, flow, recorder, qa, proof, helper_uid):
    adapter.require(adapter.RECORDER_MANIFEST_SHA == R5_MANIFEST and
                    proof['source_manifest_sha256'] == QA_MANIFEST and
                    adapter.SELF == qa.SELF == SELF,
                    'ACTUAL_BUILT_R9_ADAPTER_REQUIRED')
    return adapter.Session(flow, recorder, qa, proof, helper_uid)
