"""Match original unpublished writer retirement without inventing a head.

Reservation completion is historical metadata at the same old sequence. Its
old finite lease never becomes a new live grant. Only the actual later owner
and new native namespace can produce the separately checked CPU operation.
"""
import native_owner_continuity_types as types
import native_owner_activation_witness as current_witness
import native_owner_evidence as e
import native_owner_genesis_record as genesis
import native_owner_genesis_witness as witness
import native_owner_prior_boot_authority as authority
import native_owner_prior_boot_types as fixed


BASE_KEYS = ("initial_root", "initial_kernel_boot", "initial_cut", "genesis_sha256", "issuer_id", "verifying_key", "scopes")


def resumed(value, mode, previous, stopped, observed):
    e.obj(value, BASE_KEYS if mode == "before_writer" else (*BASE_KEYS, "unactivated_writer"),
          "actual original unpublished installation resume")
    saved, state = observed["genesis"], observed["state"]
    payload = saved["payload"]
    wanted = {"initial_root": payload["initial_root"], "initial_kernel_boot": previous["native_boot_id"],
              "initial_cut": payload["initial_cut"], "genesis_sha256": saved["payload_sha256"],
              "issuer_id": fixed.SIGNER, "verifying_key": payload["verifying_key"],
              "scopes": [item["scope_sha256"] for item in state["issuer"]["policies"]]}
    e.require({key: value[key] for key in BASE_KEYS} == wanted,
              "original cold-open did not preserve the exact initial identity, physical cut, key and observed scopes")
    if mode == "before_writer":
        return value, None
    old = e.obj(value["unactivated_writer"], ("writer", "proof", "peer", "reservation", "completed_reserved_proof", "retirement"),
                "actual original signed unpublished predecessor")
    candidate = previous["first_candidate"]
    proof = witness.proof(old["proof"])
    e.require(old["writer"] == candidate["writer"] and old["peer"] == candidate["peer"]
              and old["peer"]["boot_id"] == previous["linux_boot_id"] != state["root"]["boot_id"]
              and proof == state["issuer"]["writer_authorization"] and proof["claims"]["sequence"] == 1
              and {key: proof["claims"][key] for key in types.REGISTRATION_KEYS} == old["writer"],
              "original no-head retirement selected another signed writer or reused its actual boot/lifetime")
    if mode == "writer_reserved":
        e.require(old["reservation"] == previous["first_reservation"]["claims"]
                  and old["completed_reserved_proof"] == proof
                  and proof["claims"] == previous["first_reservation"]["claims"],
                  "original pending completion changed its actual old claims, sequence, times or complete proof")
    else:
        e.require(old["reservation"] is None and old["completed_reserved_proof"] is None
                  and proof == previous["first_writer_proof"],
                  "already signed first writer was treated as a new reservation or re-signed")
    retired = e.obj(old["retirement"], ("registry_before", "revocations_applied", "registry_after"),
                    "actual original complete unpublished lease retirement")
    before = fixed.selection(retired["registry_before"], fixed.AGENT)
    after = fixed.selection(retired["registry_after"], fixed.AGENT)
    e.require(type(stopped.get("root_authority")) is dict, "actual original stopped registry evidence required")
    authority.registry_selection(stopped["root_authority"]["registry"], before)
    receipts = retired["revocations_applied"]
    e.require(type(receipts) is list and len(receipts) == len(before["leases"])
              and after["leases"] == state["registry"]["leases"] == [],
              "unpublished recovery failed to retire the complete actual old Agent lease selection")
    revision, at = before["store_revision"], before["observed_unix_ms"]
    for issued, receipt in zip(before["leases"], receipts):
        e.obj(receipt, fixed.REVOKE_KEYS, "original actual unpublished lease revocation receipt")
        lease = types.lease(issued, fixed.AGENT,
                            20000 if issued["binding"]["operation_class"] == "runtime.agentd.production_writer" else 120000,
                            issued["binding"]["operation_class"], issued["binding"]["destination_id"])
        reason = types.sha(["native.original.unpublished-retirement.v1",
            e.ordered(state["root"], e.PEER_KEYS, "actual cold-open Root"), saved["payload_sha256"],
            [current_witness.candidate_ordered(old["writer"]), proof], lease])
        e.require(receipt["lease_id"] == issued["lease_id"] and receipt["authority_epoch"] == 1
                  and receipt["previous_lease_revision"] == 1 and receipt["lease_revision"] == 2
                  and type(receipt["store_revision"]) is int and receipt["store_revision"] == revision + 1
                  and bytes(types.digest_array(receipt["reason_sha256"], "actual unpublished retirement reason")).hex() == reason,
                  "actual original unpublished lease retirement lost its canonical revision/reason binding")
        at = e.integer(receipt["revoked_at_unix_ms"], "actual original unpublished retirement time", at)
        revision = receipt["store_revision"]
    e.require(after["store_revision"] == state["registry"]["store_revision"] == revision
              and after["observed_unix_ms"] >= at
              and state["registry"]["observed_unix_ms"] >= after["observed_unix_ms"],
              "actual empty old registry observation is detached from complete original retirement")
    return value, proof
