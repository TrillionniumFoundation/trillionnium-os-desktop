"""Use the actual r4 adapter's R4 Session without overriding any method.

The r4 build itself declares R4. Its source and recorder bindings must match;
no old R3 global is changed and no legacy constructor shim is reused.
"""
R4_MANIFEST = '52b95328e2f07aaf4416b7f48c9046ffa465337cad7a410ea3a7027512720dc1'
QA_MANIFEST = 'e54c6f0a2838f4332287224048c58f2884878b4c7bc7b3fd25be415cd0085c17'
SELF = 'org.droidloom.qa.bili.r4'


def new_session(adapter, flow, recorder, qa, proof, helper_uid):
    adapter.require(adapter.RECORDER_MANIFEST_SHA == R4_MANIFEST and
                    proof['source_manifest_sha256'] == QA_MANIFEST and
                    adapter.SELF == qa.SELF == SELF,
                    'ACTUAL_BUILT_R4_ADAPTER_REQUIRED')
    return adapter.Session(flow, recorder, qa, proof, helper_uid)
