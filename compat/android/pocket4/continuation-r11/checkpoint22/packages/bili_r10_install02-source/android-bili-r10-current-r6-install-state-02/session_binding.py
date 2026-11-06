"""Use the actual r10 adapter's R6 Session without overriding any method.

The frozen r10 source declares R6; actual build proof remains required. Its source and recorder bindings must match;
no old R3 global is changed and no legacy constructor shim is reused.
"""
R6_MANIFEST = '002ee581a4bb399536dd7d594d01f050e2540d9c049b0cfb37e1c96954b6caff'
QA_MANIFEST = '52ababa77e144bdb43f0f6fde4483e2f8cb43dcf8c431590b02b068d2715f9f2'
SELF = 'org.droidloom.qa.bili.r10'


def new_session(adapter, flow, recorder, qa, proof, helper_uid):
    adapter.require(adapter.RECORDER_MANIFEST_SHA == R6_MANIFEST and
                    proof['source_manifest_sha256'] == QA_MANIFEST and
                    adapter.SELF == qa.SELF == SELF,
                    'ACTUAL_BUILT_R10_ADAPTER_REQUIRED')
    return adapter.Session(flow, recorder, qa, proof, helper_uid)
