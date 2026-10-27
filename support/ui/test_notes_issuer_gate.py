"""Pure shape/receipt fixtures only: no cryptographic or product qualification."""
import copy
import json
import unittest
from notes_fault_contract import Refused, digest
from notes_issuer_gate_contract import IssuerTransaction, raw_member, OPERATION
import notes_issuer_gate_receipts as receipts


def encode(value):
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()


def original():
    bound = dict(subject_id="original:agentd", destination_id="trill.notes:abc:3:def",
                 request_sha256=[1]*32, scope_sha256=[2]*32, payload_sha256=[3]*32)
    select = {key:bound[key] for key in ("subject_id", "destination_id", "scope_sha256")}
    select["exact_binding"] = None
    request = dict(schema_version=1, operation=OPERATION, binding=bound)
    grant = dict(schema_version=1, signer_id="root:original", authority_epoch=3, grant_id="original:grant:1",
                 nonce=[4]*32, binding=bound, not_before_unix_ms=1000, expires_at_unix_ms=2000)
    signed = dict(grant=grant, signature=[7]*64)  # shape fixture, NOT a signature
    head = dict(authority_epoch=3, revision=8, revoked_grant_ids=["older:grant"])
    return select, request, dict(schema_version=1, revocations=head, grant=signed, denial_reason=None)


def capture_pair():
    select, request, response = original(); tx = IssuerTransaction(select)
    raw=encode(request); frame=len(raw).to_bytes(4,"big")+raw
    tx.received(frame[:1],50.0); tx.received(frame[1:3],50.01); tx.received(frame[3:],50.02)
    body=encode(response); prefix=len(body).to_bytes(4,"big")
    tx.write_entry(prefix[:1],1); tx.write_exit(1); tx.write_entry(prefix[1:],3); tx.write_exit(3)
    return tx, body


def all_receipts(capture):
    grant=capture["signed"]["grant"]; bound=capture["binding"]
    instance=dict(boot_id="original-boot",root_pid=1234,process_start_ticks=77,episode_nonce=[4]*32)
    mirror=dict(status="issued_notes_grant_observed",instance=instance,observation=dict(status="captured",
        selection_scope="volatile_original_notes_issue_artifact",signed_grant_json=capture["signed_raw"].decode(),
        signed_grant_sha256=capture["signed_grant_sha256"],observation_attempt=1,delivery_observed=False,effect_observed=False))
    lease=dict(schema_version=1,lease_id="original:effect",authority_epoch=3,revision=1,
        binding=dict(principal_id=bound["subject_id"],operation_class=OPERATION,destination_id=bound["destination_id"],
                     scope_sha256=bound["scope_sha256"],payload_sha256=bound["payload_sha256"]),
        issued_at_unix_ms=900,expires_at_unix_ms=2200)
    def sync(rev):
        return dict(state="confirmed",device_frontier=dict(authority_epoch=3,revocation_revision=rev,state_sha256=[8]*32),
                    notes_frontier=dict(authority_epoch=3,revocation_revision=rev,state_sha256=[9]*32))
    before=dict(status="original_notes_grant_observed",instance=instance,original_grant_id=grant["grant_id"],
        effect_lease=dict(lease=lease,store_revision=10),effect_revocation=None,
        lease_frontier=dict(authority_epoch=3,store_revision=10,state_sha256=[5]*32),
        final_use_head=capture["head"],grant_expired=False,synchronization=sync(8))
    receipt=dict(lease_id=lease["lease_id"],authority_epoch=3,previous_lease_revision=1,lease_revision=2,
                 store_revision=11,reason_sha256=[6]*32,revoked_at_unix_ms=1500)
    next_head=dict(authority_epoch=3,revision=9,revoked_grant_ids=sorted(["older:grant",grant["grant_id"]]))
    mutation=dict(status="original_notes_grant_revocation",instance=instance,original_grant_id=grant["grant_id"],
                  effect_lease_receipt=receipt,final_use_head=next_head,synchronization=sync(9))
    after=copy.deepcopy(before); after.update(final_use_head=next_head,synchronization=sync(9))
    after["effect_lease"]["lease"]["revision"]=2
    after["effect_lease"]["store_revision"]=after["lease_frontier"]["store_revision"]=11
    rev=dict(receipt); del rev["previous_lease_revision"]
    after["effect_revocation"]=dict(revocation=dict(schema_version=1,**rev))
    return instance,mirror,before,mutation,after


class GateContractTests(unittest.TestCase):
    def test_original_bytes_and_four_sent_header_zero_body(self):
        tx,body=capture_pair(); c=tx.write_entry(body,len(body))
        self.assertEqual(c["response_raw"],body); self.assertEqual(c["signed_raw"],encode(json.loads(body)["grant"]))
        self.assertEqual(c["request_sha256"],digest(c["request_raw"]))
        self.assertFalse(c["fresh_or_unspent_proven_by_parser"]); self.assertEqual(tx.body_sent,0)
        self.assertEqual(len(tx.header),4)

    def test_raw_nested_member_keeps_whitespace_and_unicode(self):
        raw=b' \n {"first":1,"grant" : { "x":"\\u4e2d", "n" : [1,2] },"tail":2}'
        self.assertEqual(raw_member(raw,"grant"),b'{ "x":"\\u4e2d", "n" : [1,2] }')

    def test_partial_start_and_partial_body_refused(self):
        select,request,_=original()
        with self.assertRaisesRegex(Refused,"not_original_first_byte"): IssuerTransaction(select).received(encode(request),0)
        tx,body=capture_pair()
        with self.assertRaisesRegex(Refused,"not_complete_first_grant_body"): tx.write_entry(body[:1],1)

    def test_exact_binding_mismatch_refused(self):
        select,request,_=original(); select["exact_binding"]=copy.deepcopy(request["binding"])
        request["binding"]["request_sha256"][0]=4; raw=encode(request); frame=len(raw).to_bytes(4,"big")+raw
        tx=IssuerTransaction(select); tx.received(frame[:1],0)
        with self.assertRaisesRegex(Refused,"exact_mismatch"): tx.received(frame[1:],0)

    def test_other_policy_passes_without_capture(self):
        select,request,response=original(); select["subject_id"]="another:agentd"
        tx=IssuerTransaction(select); raw=encode(request); frame=len(raw).to_bytes(4,"big")+raw
        tx.received(frame[:1],0); tx.received(frame[1:],0); body=encode(response)
        tx.write_entry(len(body).to_bytes(4,"big"),4); tx.write_exit(4)
        self.assertIsNone(tx.write_entry(None,len(body))); tx.write_exit(len(body))
        self.assertEqual(tx.completed_other_frames,1)

    def test_duplicate_unknown_denial_and_pre_revoked_refused(self):
        _,_,response=original(); revoked=copy.deepcopy(response)
        revoked["revocations"]["revoked_grant_ids"]=[revoked["grant"]["grant"]["grant_id"]]
        variants=[encode(response).replace(b'"schema_version":1',b'"schema_version":1,"schema_version":1',1),
                  encode(dict(response,unknown=True)),encode(dict(response,grant=None,denial_reason="refused")),encode(revoked)]
        for raw in variants:
            with self.subTest(sha=digest(raw)):
                tx,_=capture_pair(); tx.response_length=len(raw)
                with self.assertRaises(Refused): tx.write_entry(raw,len(raw))

    def test_grant_epoch_nonce_time_binding_and_signature_shape_rejected(self):
        mutators=[lambda g:g["grant"].update(authority_epoch=4),lambda g:g["grant"].update(nonce=[0]*32),
                  lambda g:g["grant"].update(expires_at_unix_ms=1000),lambda g:g.update(signature=[1]*63),
                  lambda g:g["grant"]["binding"].update(payload_sha256=[9]*32)]
        for mutate in mutators:
            tx,body=capture_pair(); response=json.loads(body); mutate(response["grant"]); raw=encode(response)
            tx.response_length=len(raw)
            with self.assertRaises(Refused): tx.write_entry(raw,len(raw))

    def test_same_root_full_chain_and_distinct_valid_consumer_nonce_histories(self):
        tx,body=capture_pair(); c=tx.write_entry(body,len(body)); i,m,b,r,a=all_receipts(c)
        receipts.mirror(m,c,i); receipts.before_revoke(b,c,i)
        receipts.revoked(r,c,i,b,"06"*32); receipts.after_revoke(a,c,i,b,r)

    def test_mirror_requires_actual_bytes_not_reserialization(self):
        tx,body=capture_pair(); c=tx.write_entry(body,len(body)); i,m,*_=all_receipts(c)
        m["observation"]["signed_grant_json"]=json.dumps(c["signed"])
        with self.assertRaisesRegex(Refused,"mirror_bytes"): receipts.mirror(m,c,i)

    def test_unknown_pending_expired_wrong_root_binding_and_cas_refused(self):
        tx,body=capture_pair(); c=tx.write_entry(body,len(body)); i,_,b,r,a=all_receipts(c)
        checks=[(b,lambda v:v.update(grant_expired=True),lambda v:receipts.before_revoke(v,c,i)),
            (b,lambda v:v["instance"]["episode_nonce"].__setitem__(0,2),lambda v:receipts.before_revoke(v,c,i)),
            (b,lambda v:v["effect_lease"]["lease"]["binding"].update(payload_sha256=[1]*32),lambda v:receipts.before_revoke(v,c,i)),
            (r,lambda v:v.update(final_use_head=None),lambda v:receipts.revoked(v,c,i,b,"06"*32)),
            (r,lambda v:v.update(synchronization={"state":"pending","reason":"not synced"}),lambda v:receipts.revoked(v,c,i,b,"06"*32)),
            (r,lambda v:v["effect_lease_receipt"].update(revoked_at_unix_ms=2000),lambda v:receipts.revoked(v,c,i,b,"06"*32)),
            (r,lambda v:v["effect_lease_receipt"].update(previous_lease_revision=2),lambda v:receipts.revoked(v,c,i,b,"06"*32)),
            (a,lambda v:v["synchronization"]["notes_frontier"].update(revocation_revision=8),lambda v:receipts.after_revoke(v,c,i,b,r)),
            (a,lambda v:v["effect_revocation"]["revocation"].update(reason_sha256=[7]*32),lambda v:receipts.after_revoke(v,c,i,b,r))]
        for initial,mutate,check in checks:
            value=copy.deepcopy(initial); mutate(value)
            with self.subTest(change=mutate):
                with self.assertRaises(Refused): check(value)


if __name__=="__main__": unittest.main()
