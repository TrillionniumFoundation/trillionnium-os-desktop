#!/usr/bin/env python3
"""Metadata-only semantic controls; no network, payload, SDK or Android action."""
import copy
import importlib.util
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('late_public_metadata',HERE/'verify_late_metadata.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
BUSINESS={'path':'compat/android/pocket4/current-app-acceptance/system-cp3a-provider-source-20261119/current/CURRENT-BUSINESS-PLAN.json',
          'bytes':146172,'sha256':'8f209ce7c4be9d8330f8a4280babcb2ad8f62595b6fb5462adb3b0e88c7d282e'}


class Controls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs,cls.expected=m.load_inputs()
        cls.sources={key:(HERE.parent/'united/actual'/name).read_bytes() for key,name in [
            ('current_source_state','CURRENT-SOURCE-STATE.json'),
            ('current_registry','current-source-inputs.json'),
            ('current_freshness','current-source-freshness.json')]}

    def reject(self, change, match):
        data=copy.deepcopy(self.docs);change(data)
        with self.assertRaisesRegex(ValueError,match):
            m.derive(data,self.expected,self.sources,BUSINESS)

    def test_actual_complete_summary_reconstruction(self):
        result=m.verify(self.sources,BUSINESS)
        self.assertEqual(result['matching_public_version_or_exact_build_observations'],28)
        self.assertEqual(result['publisher_body_identity_pending_at_observation'],['com.szzc'])
        self.assertEqual(result['actual_metadata_units_retired'],5)
        self.assertIs(result['all39_latest_qualified'],False)
        self.assertIs(result['HTTP_bodies_reparsed_by_this_consumer'],False)

    def test_public_metadata_cannot_extend_Play_expiry(self):
        self.reject(lambda d:d['PLAN.json'].__setitem__('original_GET_ITEMS_expires_utc','2026-11-20T17:44:09.086253+00:00'),'expiry is never renewed')

    def test_public_metadata_cannot_grant_latest_credit(self):
        self.reject(lambda d:d['actual/PARSED-OBSERVATIONS.json'].__setitem__('all39_latest_qualified',True),'cannot promote')

    def test_publisher_header_cannot_qualify_source_identity(self):
        self.reject(lambda d:d['actual/PUBLISHER-REDIRECT-HEAD.json'].__setitem__('source_identity_requalified',True),'cannot promote')

    def test_wrong_Play_primary_package_rejected(self):
        def change(d):
            row=next(r for r in d['actual/PARSED-OBSERVATIONS.json']['rows'] if r['package']=='com.Hyatt.hyt')
            row['observation']['package_identity']='unrelated.package'
        self.reject(change,'primary public application identity')

    def test_Fcitx_tag_without_selected_build_asset_rejected(self):
        def change(d):
            row=next(r for r in d['actual/PARSED-OBSERVATIONS.json']['rows'] if r['package']=='org.fcitx.fcitx5.android')
            row['observation']['assets'].pop()
        self.reject(change,'exact Fcitx build assets')

    def test_omitted_original_timeout_retry_rejected(self):
        def change(d):d['actual/TWO-TIMEOUT-RETRY.json']['rows'].pop()
        self.reject(change,'only the two observed timeouts')

    def test_mirror_metadata_cannot_be_promoted_to_publisher(self):
        def change(d):d['actual/SELECTED-ORIGIN-SUPPLEMENT.json']['rows'][0]['mirror_metadata_is_not_publisher_or_signature_verification']=False
        self.reject(change,'matching original mirror is metadata only')

    def test_publisher_HEAD_does_not_prove_version(self):
        self.reject(lambda d:d['actual/PUBLISHER-REDIRECT-HEAD.json'].__setitem__('version_observed_from_headers','9.6.3'),'no inferred version')

    def test_unrecorded_SDK_action_rejected(self):
        self.reject(lambda d:d['actual/SELECTED-ORIGIN-SUPPLEMENT.json'].__setitem__('SDK_or_Android_calls',1),'no payload/SDK/Android')

    def test_incomplete_actual_client_rejected(self):
        self.reject(lambda d:d['actual/retry-execution.json'].__setitem__('output_complete',False),'actual original metadata client')

    def test_retirement_requires_actual_absent_cgroup(self):
        # Change the embedded observation while preserving its own transcript
        # SHA/length so this exercises the semantic gate beyond the outer pin.
        def change(d):
            doc=d['actual/metadata-units-retirement.json'];row=m.strict_json(doc['text'])
            row['units'][0]['cgroup_exists']=True
            doc['text']=m.json.dumps(row,sort_keys=True)+'\r\n';raw=doc['text'].encode()
            doc['chunk_sha256']=m.hashlib.sha256(raw).hexdigest()
            doc['next_offset']=doc['available_end']=len(raw)
            doc['status']['bytes_seen']=doc['status']['bytes_stored']=len(raw)
        self.reject(change,'actual exact unit and cgroup absence')

    def test_duplicate_JSON_identity_rejected(self):
        with self.assertRaisesRegex(ValueError,'duplicate metadata key'):
            m.strict_json('{"package":"expected","package":"other"}')


if __name__=='__main__':
    unittest.main(verbosity=2)
