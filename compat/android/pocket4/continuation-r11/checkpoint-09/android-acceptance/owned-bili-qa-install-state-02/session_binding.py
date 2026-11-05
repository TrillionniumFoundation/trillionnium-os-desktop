"""Explicit host-only R4 recorder binding; actual compiled QA source stays fixed.

The five operational Session methods are inherited unchanged from the pinned
actual-build QA adapter. This constructor declares the new recorder dependency;
it neither edits that adapter's global R3 pin nor forges a R3 SourceContract.
"""
R3_MANIFEST = '4ff896b75c4c7751a28eee34ab512583c3a26eb43f5e28598a776d40ee496906'
R4_MANIFEST = '52b95328e2f07aaf4416b7f48c9046ffa465337cad7a410ea3a7027512720dc1'
QA_MANIFEST = 'd0f9f0f45d0e94a3d6b4a46e0ae0d9048ea2e6ff6c60550b39f54a75029d5aba'


def new_session(adapter, flow, recorder, qa, proof, helper_uid):
    adapter.require(adapter.RECORDER_MANIFEST_SHA == R3_MANIFEST and
                    proof['source_manifest_sha256'] == QA_MANIFEST,
                    'ACTUAL_BUILT_QA_BASE_ADAPTER_REQUIRED')
    class RecorderR4Session(adapter.Session):
        def __init__(self):
            adapter.require(flow.contract.sha256 == R4_MANIFEST and not flow._private_backend_transport,
                            'EXACT_NEW_R4_PUBLIC_TRANSPORT_REQUIRED')
            adapter.require(type(helper_uid) is int and 10000 <= helper_uid < 100000 and
                            helper_uid not in (10117,10125), 'EXACT_NEW_OWNED_HELPER_UID_REQUIRED')
            self.flow, self.recorder, self.qa, self.proof, self.uid = flow, recorder, qa, proof, helper_uid
            self.nonces = set()
    return RecorderR4Session()
