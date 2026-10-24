"""Check bytes of original retained Root launch observations after a guest run.

These are bounded original Root lifecycle observations, never Current receipts
or an alternative D/K ledger. Disk extraction, actual ownership/mode checks,
event order and source-bound native execution remain independent requirements.
No scenario can pass by calling these structural helpers alone.
"""
import hashlib

from native_owner_evidence import byte_id, canonical, integer, json_value, obj, require, text
from native_owner_successor_wire import exact_bytes, launch_receipt, retirement_receipt


ROOT_OBSERVATION_DIRECTORY = "/state/hepta-native/protected-source/authority/native-launch-observations"
MAX_OBSERVATION_BYTES = 16_384
PAYLOAD_KEYS = ("schema_version", "operation", "boot_id", "launch_generation",
                "launch_receipt", "retirement_receipt")


def launch_observation_id(boot_id, generation):
    boot_id = byte_id(boot_id, "original launch observation boot")
    generation = integer(generation, "actual kernel launch generation", 1)
    return "native-launch:" + bytes(boot_id).hex() + ":" + format(generation, "016x")


def launch_observation_filename(observation_id):
    text(observation_id, "original Root observation ID")
    return "observation-v1-" + hashlib.sha256(observation_id.encode("utf-8")).hexdigest() + ".json"


def inspect_saved_launch(raw, expected_boot, expected_generation, actual_payload_json):
    """Match an actual file's complete contents to the original returned payload."""
    require(type(raw) is bytes and 0 < len(raw) <= MAX_OBSERVATION_BYTES,
            "Root observation exceeds the original file bound")
    expected_id = launch_observation_id(expected_boot, expected_generation)
    stored = obj(json_value(raw), ("schema_version", "observation_id", "payload"),
                 "original RootStoredObservation file")
    require(type(stored["schema_version"]) is int and stored["schema_version"] == 1
            and stored["observation_id"] == expected_id,
            "stored original Root observation changed version or identity")
    require(type(actual_payload_json) is str and 0 < len(actual_payload_json.encode("utf-8")) <= MAX_OBSERVATION_BYTES,
            "actual returned Root launch payload is not bounded UTF-8")
    payload_bytes = exact_bytes(stored["payload"], len(actual_payload_json.encode("utf-8")),
                                "stored original Root launch payload")
    require(payload_bytes == actual_payload_json.encode("utf-8"),
            "retained disk observation differs from the actual returned Root payload bytes")
    original_record = {"schema_version": 1, "observation_id": expected_id, "payload": list(payload_bytes)}
    require(raw == canonical(original_record).encode("utf-8"),
            "retained Root file differs from the original ObservationRecord serialization")
    payload = obj(json_value(payload_bytes), PAYLOAD_KEYS, "original Root launch observation payload")
    require(type(payload["schema_version"]) is int and payload["schema_version"] == 1
            and payload["operation"] == "kernel.g2.launch-observation.v1"
            and byte_id(payload["boot_id"], "stored native boot") == expected_boot
            and type(payload["launch_generation"]) is int
            and payload["launch_generation"] == expected_generation,
            "Root lifecycle payload changed operation, boot or launch generation")
    launched = launch_receipt(payload["launch_receipt"], expected_boot)
    retired = retirement_receipt(payload["retirement_receipt"], expected_boot)
    require(launched["generation"] == retired["generation"] == expected_generation,
            "stored launch and final retirement cuts bind different generations")
    return {"observation_id": expected_id, "filename": launch_observation_filename(expected_id),
            "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "payload_sha256": hashlib.sha256(payload_bytes).hexdigest(),
            "launch": launched, "retirement": retired}
