"""Signed-input and transactional D6 regressions; no actual network or portal."""
from __future__ import annotations
import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest
from tests.d6 import test_capability_egress_reference as support
import capability_egress_reference as api

ROOT = Path(__file__).resolve().parents[2]

class CapabilityBoundaryHardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        support.CapabilityEgressTests.setUpClass()
        cls.helper = support.CapabilityEgressTests()
        cls.helper.setUp()
        cls.permit = cls.helper.network_permit(maximum_uses=8)
        cls.file_permit = cls.helper.file_permit(maximum_uses=1)

    def decide(self, request=None, permit=None, **kwargs):
        return self.helper.decision([permit or self.permit], request or api.fixture_network_request(), **kwargs)

    def unchanged_denial(self, callback, ledger):
        before = copy.deepcopy((ledger.uses, ledger.receipts))
        with self.assertRaises(api.PolicyError):
            callback()
        self.assertEqual((ledger.uses, ledger.receipts), before)

    def test_url_controls_are_not_silently_removed(self):
        for bad in ['\t', '\r', '\n', '\0', '\x1f', ' ', '\x7f', '\u00a0']:
            for url in [f'https://exa{bad}mple.com/path', bad + 'https://example.com/path']:
                with self.subTest(url=repr(url)), self.assertRaises(api.PolicyError):
                    api.split_url(url, ['https', 'wss'])
        r = api.fixture_network_request(); r['url'] = 'https://exa\tmple.com/path'
        ledger = api.DecisionLedger()
        self.unchanged_denial(lambda: self.decide(r, ledger=ledger), ledger)

    def test_noncanonical_url_authority_is_rejected(self):
        for url in ['HTTPS://example.com/path', 'https://EXAMPLE.com/path',
                    'https://example.com:0443/path', 'https://example.com:/path',
                    'https://example.com/#', 'https://example.com\\x/path']:
            with self.subTest(url=url), self.assertRaises(api.PolicyError):
                api.split_url(url, ['https', 'wss'])

    def test_valid_urls_remain_accepted(self):
        for url in ['https://example.com/path', 'https://example.com:443/path',
                    'https://example.com/%20?q=a%20b', 'wss://example.com/socket']:
            self.assertEqual(api.split_url(url, ['https', 'wss'])[1], 'example.com')

    def test_boolean_request_integer_fields_are_rejected(self):
        for field in ['request_bytes', 'expected_response_bytes', 'redirect_count']:
            for value in [True, False]:
                with self.subTest(field=field, value=value):
                    request = api.fixture_network_request(); request[field] = value
                    with self.assertRaises(api.PolicyError): self.decide(request)

    def test_boolean_signed_permit_fields_are_rejected(self):
        for field in ['issued_at_epoch', 'not_before_epoch', 'expires_at_epoch', 'maximum_uses']:
            with self.subTest(field=field):
                permit = copy.deepcopy(self.permit); permit[field] = True
                self.helper.resign(permit)
                with self.assertRaises(api.PolicyError): self.decide(permit=permit)

    def test_boolean_uid_and_invalid_runtime_times_are_rejected(self):
        for value in [True, False]:
            subject = api.fixture_subject(); subject['mechanism_uid'] = value
            with self.assertRaises(api.PolicyError): api.canonical_subject(subject)
        for value in [True, False, -1, 100.0]:
            with self.assertRaises(api.PolicyError): self.decide(now_epoch=value)

    def test_dns_and_connection_times_are_bound(self):
        for field in ['ttl_seconds', 'observed_at_epoch']:
            request = api.fixture_network_request(); request['dns'][field] = True
            with self.assertRaises(api.PolicyError): self.decide(request)
        for value in [True, -1, 0]:
            request = api.fixture_network_request(); request['connection']['observed_at_epoch'] = value
            with self.assertRaises(api.PolicyError): self.decide(request)

    def test_file_bytes_are_not_booleans(self):
        request = {'kind':'file','action':'write','handle_id':'file-handle-1','bytes':True}
        with self.assertRaises(api.PolicyError): api.authorize_file(self.file_permit, request)

    def test_notification_text_is_not_stringified(self):
        permit = {'audience':'portal:notification','actions':['show'],
                  'resource':{'kind':'notification_channel','channel_id':'c','maximum_text_bytes':128}}
        for value in [True, {}, [], 1, None]:
            request = {'kind':'notification','action':'show','channel_id':'c','title':value,'body':'x'}
            with self.assertRaises(api.PolicyError): api.authorize_notification(permit, request)
        permit['resource']['maximum_text_bytes'] = True
        request = {'kind':'notification','action':'show','channel_id':'c','title':'','body':''}
        with self.assertRaises(api.PolicyError): api.authorize_notification(permit, request)

    def test_audio_limits_are_not_booleans(self):
        permit = {'audience':'portal:audio','actions':['play'],
                  'resource':{'kind':'audio_stream','stream_id':'s','maximum_duration_ms':True,'maximum_gain_millibel':0}}
        request = {'kind':'audio','action':'play','stream_id':'s','duration_ms':1,'gain_millibel':0}
        with self.assertRaises(api.PolicyError): api.authorize_audio(permit, request)

    def test_encoding_failure_does_not_consume_permit(self):
        for bad in [object(), float('nan'), float('inf'), '\ud800']:
            ledger = api.DecisionLedger()
            self.unchanged_denial(lambda: ledger.commit([self.file_permit], {'bad':bad}, {}, 100), ledger)
            self.unchanged_denial(lambda: ledger.commit([self.file_permit], {}, {'bad':bad}, 100), ledger)

    def test_second_permit_failure_rolls_back_first(self):
        other = copy.deepcopy(self.file_permit); other['permit_id'] = 'other'
        ledger = api.DecisionLedger(uses={'other':1})
        self.unchanged_denial(lambda: ledger.commit([self.file_permit,other], {}, {}, 100), ledger)

    def test_duplicate_and_unused_permits_are_rejected(self):
        ledger = api.DecisionLedger()
        self.unchanged_denial(lambda: ledger.commit([self.file_permit,self.file_permit], {}, {}, 100), ledger)
        self.unchanged_denial(lambda: self.helper.decision([self.permit,self.permit], ledger=ledger), ledger)
        self.unchanged_denial(lambda: self.helper.decision([self.permit,self.file_permit], ledger=ledger), ledger)

    def test_concurrent_single_use_consumes_exactly_once(self):
        ledger = api.DecisionLedger()
        def attempt(_index):
            try:
                ledger.commit([self.file_permit], {}, {}, 100); return True
            except api.PolicyError: return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(attempt, range(32)))
        self.assertEqual(sum(results), 1)
        self.assertEqual(ledger.uses, {'permit-file':1})
        self.assertEqual(len(ledger.receipts), 1)
        api.DecisionLedger.verify_receipts(ledger.receipts)

    def test_receipt_return_is_detached_and_effect_claim_cannot_be_rehashed(self):
        ledger = api.DecisionLedger()
        receipt = ledger.commit([self.file_permit], {}, {'nested':[]}, 100)
        receipt['details']['nested'].append('tamper')
        self.assertEqual(ledger.receipts[0]['details']['nested'], [])
        api.DecisionLedger.verify_receipts(ledger.receipts)
        receipt = copy.deepcopy(ledger.receipts[0]); receipt['external_effect_executed'] = True
        receipt.pop('receipt_sha256'); receipt['receipt_sha256'] = api.sha256(api.canonical_json(receipt))
        with self.assertRaises(api.PolicyError): api.DecisionLedger.verify_receipts([receipt])

    def test_json_duplicate_members_nonfinite_and_byte_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'input.json'
            for content in ['{"a":1,"a":2}', '{"x":{"a":1,"a":2}}', '{"x":NaN}', '{"x":Infinity}', ' '*(api.MAX_JSON_BYTES+1)]:
                path.write_text(content)
                with self.assertRaises(api.PolicyError): api.load_json(path)
            path.write_text('{"a":1}')
            self.assertEqual(api.load_json(path), {'a':1})

    def test_v2_schema_field_set_matches_reference(self):
        schema = json.loads((ROOT/'contracts/capability-permit.v2.schema.json').read_text())
        self.assertEqual(set(schema['required']), api.PERMIT_FIELDS)
        self.assertEqual(set(schema['properties']), api.PERMIT_FIELDS)
        self.assertFalse(schema['additionalProperties'])
        self.assertEqual(schema['properties']['schema']['const'], api.PERMIT_SCHEMA)
        self.assertEqual(set(schema['properties']['subject']['required']), api.SUBJECT_FIELDS)
        self.assertEqual(self.permit['schema'], api.PERMIT_SCHEMA)
        self.assertEqual(self.helper.contract['permit']['schema'], api.PERMIT_SCHEMA)
        legacy = json.loads((ROOT/'contracts/capability-permit.v1.schema.json').read_text())
        self.assertNotEqual(legacy['properties']['schema']['const'], api.PERMIT_SCHEMA)

    def test_signed_legacy_schema_is_rejected(self):
        permit = copy.deepcopy(self.permit); permit['schema'] = 'trillionnium.desktop.capability-permit.v1'
        self.helper.resign(permit)
        with self.assertRaises(api.PolicyError): self.decide(permit=permit)

if __name__ == '__main__': unittest.main()
