"""Strict comparison of actual same-Root admin replies, not grant authority.

Only the pinned Root CLI obtains these replies. This pure module never sends,
updates a frontier, authenticates a signature or concludes consumer acceptance.
"""
from notes_fault_contract import digest, fields, require, uint
from notes_issuer_gate_contract import head, octets, identifier


def same_instance(response, instance):
    require(response.get("instance") == instance, "admin_root_instance_mismatch")


def grant_identity(response, capture, instance):
    same_instance(response, instance)
    require(response["original_grant_id"] == capture["signed"]["grant"]["grant_id"], "admin_grant_mismatch")


def mirror(response, capture, instance):
    fields(response, ("status", "instance", "observation"))
    require(response["status"] == "issued_notes_grant_observed", "original_mirror_unavailable")
    same_instance(response, instance)
    value = response["observation"]
    fields(value, ("status", "selection_scope", "signed_grant_json", "signed_grant_sha256",
                   "observation_attempt", "delivery_observed", "effect_observed"))
    require(value["status"] == "captured" and value["selection_scope"] == "volatile_original_notes_issue_artifact"
            and value["delivery_observed"] is False and value["effect_observed"] is False,
            "original_mirror_not_capture")
    require(type(value["signed_grant_json"]) is str and value["signed_grant_json"].encode() == capture["signed_raw"]
            and value["signed_grant_sha256"] == capture["signed_grant_sha256"]
            and uint(value["observation_attempt"]) and value["observation_attempt"] > 0, "original_mirror_bytes")


def confirmed(value, expected_head):
    fields(value, ("state", "device_frontier", "notes_frontier"))
    require(value["state"] == "confirmed", "authenticated_consumers_pending")
    for key in ("device_frontier", "notes_frontier"):
        frontier = value[key]
        fields(frontier, ("authority_epoch", "revocation_revision", "state_sha256"))
        require(uint(frontier["authority_epoch"]) and uint(frontier["revocation_revision"])
                and frontier["authority_epoch"] == expected_head["authority_epoch"]
                and frontier["revocation_revision"] == expected_head["revision"], "authenticated_frontier_mismatch")
        octets(frontier["state_sha256"], 32)


def lease_read(value, capture):
    fields(value, ("lease", "store_revision"))
    lease = value["lease"]
    fields(lease, ("schema_version", "lease_id", "authority_epoch", "revision", "binding",
                   "issued_at_unix_ms", "expires_at_unix_ms"))
    grant = capture["signed"]["grant"]
    require(type(lease["schema_version"]) is int and lease["schema_version"] == 1
            and lease["authority_epoch"] == grant["authority_epoch"]
            and identifier(lease["lease_id"])
            and uint(lease["revision"]) and lease["revision"] > 0
            and uint(value["store_revision"]) and value["store_revision"] > 0, "original_lease_identity")
    bound = lease["binding"]
    fields(bound, ("principal_id", "operation_class", "destination_id", "scope_sha256", "payload_sha256"))
    expected = capture["binding"]
    require(bound["principal_id"] == expected["subject_id"]
            and bound["destination_id"] == expected["destination_id"]
            and bound["scope_sha256"] == expected["scope_sha256"]
            and bound["payload_sha256"] == expected["payload_sha256"]
            and bound["operation_class"] == "runtime.agentd.production_operation", "original_effect_lease_binding")
    require(uint(lease["issued_at_unix_ms"]) and uint(lease["expires_at_unix_ms"])
            and lease["issued_at_unix_ms"] <= grant["not_before_unix_ms"]
            and lease["expires_at_unix_ms"] >= grant["expires_at_unix_ms"], "original_effect_lease_time")
    return lease


def observed(response, capture, instance):
    fields(response, ("status", "instance", "original_grant_id", "effect_lease", "effect_revocation",
                      "lease_frontier", "final_use_head", "grant_expired", "synchronization"))
    require(response["status"] == "original_notes_grant_observed" and response["grant_expired"] is False,
            "grant_unknown_or_expired")
    grant_identity(response, capture, instance)
    lease_read(response["effect_lease"], capture)
    actual_head = head(response["final_use_head"])
    require(actual_head["authority_epoch"] == capture["head"]["authority_epoch"], "observation_epoch")
    frontier = response["lease_frontier"]
    fields(frontier, ("authority_epoch", "store_revision", "state_sha256"))
    require(uint(frontier["authority_epoch"]) and uint(frontier["store_revision"])
            and frontier["authority_epoch"] == actual_head["authority_epoch"]
            and frontier["store_revision"] == response["effect_lease"]["store_revision"], "lease_frontier_mismatch")
    octets(frontier["state_sha256"], 32)
    return response


def before_revoke(response, capture, instance):
    observed(response, capture, instance)
    require(response["effect_revocation"] is None and response["final_use_head"] == capture["head"],
            "grant_not_original_unrevoked_head")
    # This proves original lease/head state, not lack of a consumer spend.
    confirmed(response["synchronization"], capture["head"])
    return response


def revoked(response, capture, instance, before, reason):
    fields(response, ("status", "instance", "original_grant_id", "effect_lease_receipt",
                      "final_use_head", "synchronization"))
    require(response["status"] == "original_notes_grant_revocation", "revoke_unknown")
    grant_identity(response, capture, instance)
    receipt = response["effect_lease_receipt"]
    fields(receipt, ("lease_id", "authority_epoch", "previous_lease_revision", "lease_revision",
                     "store_revision", "reason_sha256", "revoked_at_unix_ms"))
    lease = before["effect_lease"]["lease"]
    grant = capture["signed"]["grant"]
    require(all(uint(receipt[key]) for key in ("authority_epoch", "previous_lease_revision",
            "lease_revision", "store_revision", "revoked_at_unix_ms"))
            and receipt["lease_id"] == lease["lease_id"] and receipt["authority_epoch"] == lease["authority_epoch"]
            and receipt["previous_lease_revision"] == lease["revision"]
            and receipt["lease_revision"] == lease["revision"] + 1
            and receipt["store_revision"] == before["effect_lease"]["store_revision"] + 1
            and receipt["reason_sha256"] == list(bytes.fromhex(reason))
            and uint(receipt["revoked_at_unix_ms"])
            and grant["not_before_unix_ms"] <= receipt["revoked_at_unix_ms"] < grant["expires_at_unix_ms"],
            "revoke_receipt_mismatch")
    expected_head = dict(capture["head"], revision=capture["head"]["revision"] + 1,
                         revoked_grant_ids=sorted(capture["head"]["revoked_grant_ids"] + [grant["grant_id"]]))
    require(response["final_use_head"] == expected_head, "revoke_head_mismatch_or_partial")
    confirmed(response["synchronization"], expected_head)
    return response


def after_revoke(response, capture, instance, before, mutation):
    observed(response, capture, instance)
    expected_lease = dict(before["effect_lease"]["lease"], revision=mutation["effect_lease_receipt"]["lease_revision"])
    require(response["effect_lease"]["lease"] == expected_lease
            and response["effect_lease"]["store_revision"] == mutation["effect_lease_receipt"]["store_revision"]
            and response["final_use_head"] == mutation["final_use_head"], "readonly_revoke_state_mismatch")
    fields(response["effect_revocation"], ("revocation",))
    revocation = response["effect_revocation"]["revocation"]
    expected = {key: value for key, value in mutation["effect_lease_receipt"].items()
                if key != "previous_lease_revision"}
    expected["schema_version"] = 1
    require(revocation == expected, "readonly_effect_revocation_mismatch")
    confirmed(response["synchronization"], mutation["final_use_head"])
