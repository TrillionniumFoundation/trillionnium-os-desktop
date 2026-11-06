"""Use the actual r8 adapter's R4 Session without overriding any method.

The r8 build itself declares R4. Its source and recorder bindings must match;
no old R3 global is changed and no legacy constructor shim is reused.
"""
R4_MANIFEST = '52b95328e2f07aaf4416b7f48c9046ffa465337cad7a410ea3a7027512720dc1'
QA_MANIFEST = '8e3454bcc9ebe1ff55dcaf62706ce1176cfa1d0f0ede7099cbbfa46f4ad53f1e'
SELF = 'org.droidloom.qa.bili.r8'


def new_session(adapter, flow, recorder, qa, proof, helper_uid):
    adapter.require(adapter.RECORDER_MANIFEST_SHA == R4_MANIFEST and
                    proof['source_manifest_sha256'] == QA_MANIFEST and
                    adapter.SELF == qa.SELF == SELF,
                    'ACTUAL_BUILT_R8_ADAPTER_REQUIRED')
    return adapter.Session(flow, recorder, qa, proof, helper_uid)
