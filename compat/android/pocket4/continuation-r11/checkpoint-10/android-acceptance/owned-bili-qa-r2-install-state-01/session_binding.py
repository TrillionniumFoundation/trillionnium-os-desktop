"""Use the actual r2 adapter's R4 Session without overriding any method.

The r2 build itself declares R4. Its source and recorder bindings must match;
no old R3 global is changed and no legacy constructor shim is reused.
"""
R4_MANIFEST = '52b95328e2f07aaf4416b7f48c9046ffa465337cad7a410ea3a7027512720dc1'
QA_MANIFEST = 'd0214aa3c8be57d26722ae0f5ee5ac6d24bc78fb27fc97df85bb8af0d140f7df'
SELF = 'org.droidloom.qa.bili.r2'


def new_session(adapter, flow, recorder, qa, proof, helper_uid):
    adapter.require(adapter.RECORDER_MANIFEST_SHA == R4_MANIFEST and
                    proof['source_manifest_sha256'] == QA_MANIFEST and
                    adapter.SELF == qa.SELF == SELF,
                    'ACTUAL_BUILT_R2_R4_ADAPTER_REQUIRED')
    return adapter.Session(flow, recorder, qa, proof, helper_uid)
