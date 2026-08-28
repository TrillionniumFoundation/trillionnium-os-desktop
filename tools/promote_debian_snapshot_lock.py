#!/usr/bin/env python3
"""Promote an exact regenerated D0R-02 report into canonical repository state.

The script is intentionally deterministic and idempotent. It accepts only the
previously qualified lock bytes and updates the lock, selection, evidence,
current-state, plan checkpoint and machine-readable state in one working-tree
transaction. The workflow commits all changed paths in one Git commit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

EXPECTED_LOCK_SHA256 = "cd7118481f0b6875d16352b682a8880da923b44893cab884483b307abb64deae"
EXPECTED_PACKAGE_SET_SHA256 = "89918a968afafdbabe03e43794565cb1dc936f3f24a09ec81030be4a4085333a"
QUALIFYING_SOURCE_HEAD = "6825f9bd4bd012212559d187315bca285a6ae3d2"
QUALIFYING_MERGE_REF = "2c019cb8f42423af42f518cdf5d434789991b0aa"
QUALIFYING_RUN_ID = 33196743127
QUALIFYING_ARTIFACT_ID = 9696135492
QUALIFYING_ARTIFACT_NAME = (
    "debian-snapshot-lock-2c019cb8f42423af42f518cdf5d434789991b0aa"
)
QUALIFYING_ARTIFACT_SHA256 = (
    "a55b04bb56b94fe5fa4dd055fc38e71e535be1d45bcfb4071176c0cdc6f3e9f8"
)
LOCK_RELATIVE = Path("manifests/debian-snapshot.lock.v1.json")


def read_json(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise RuntimeError(f"{path} must contain a JSON object")
    return document


def write_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def replace_once_or_already(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected one promotion marker in {path}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def validate_generated_lock(raw: bytes, lock: dict[str, Any]) -> None:
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_LOCK_SHA256:
        raise RuntimeError(
            f"generated lock bytes changed: {digest} != {EXPECTED_LOCK_SHA256}"
        )
    if lock.get("schema") != "trillionnium.desktop.debian-snapshot-lock.v1":
        raise RuntimeError("unexpected generated lock schema")
    if lock.get("status") != "PASS_SIGNED_INPUT_AND_PACKAGE_CLOSURE_ONLY":
        raise RuntimeError("generated lock did not pass D0R-02")
    if lock.get("snapshot_timestamp") != "20260828T000000Z":
        raise RuntimeError("generated lock timestamp changed")
    if lock.get("architecture") != "amd64":
        raise RuntimeError("generated lock architecture changed")
    if lock.get("resolved_package_count") != 319:
        raise RuntimeError("generated package count changed")
    if lock.get("resolved_package_count") != len(lock.get("packages", [])):
        raise RuntimeError("generated package count does not match package entries")
    if lock.get("package_set_sha256") != EXPECTED_PACKAGE_SET_SHA256:
        raise RuntimeError("generated package-set digest changed")
    if len(lock.get("inrelease", [])) != 3:
        raise RuntimeError("generated lock does not contain three InRelease records")
    if any(value is not False for value in lock.get("claims", {}).values()):
        raise RuntimeError("generated lock exceeds the input-only claim ceiling")


def promote_selection(root: Path, lock: dict[str, Any]) -> None:
    path = root / "manifests/debian-base.selection.json"
    selection = read_json(path)
    selection["snapshot_lock"] = {
        "resolved": True,
        "lock_file": str(LOCK_RELATIVE),
        "canonical_lock_file_sha256": EXPECTED_LOCK_SHA256,
        "snapshot_timestamp": lock["snapshot_timestamp"],
        "resolved_package_count": lock["resolved_package_count"],
        "package_set_sha256": lock["package_set_sha256"],
        "archive_keyring_sha256": lock["archive_keyring"]["sha256"],
        "inrelease_sha256": {
            item["id"]: item["sha256"] for item in lock["inrelease"]
        },
        "accepted_primary_fingerprints": sorted(
            {
                value
                for item in lock["inrelease"]
                for value in item["accepted_primary_fingerprints"]
            }
        ),
        "resolution_provenance": {
            "source_head": QUALIFYING_SOURCE_HEAD,
            "pull_request_merge_ref": QUALIFYING_MERGE_REF,
            "workflow_run_id": QUALIFYING_RUN_ID,
            "workflow_artifact_id": QUALIFYING_ARTIFACT_ID,
            "workflow_artifact_name": QUALIFYING_ARTIFACT_NAME,
            "workflow_artifact_sha256": QUALIFYING_ARTIFACT_SHA256,
        },
        "claim_ceiling": (
            "signed_input_and_package_closure_only_no_rootfs_no_image_no_boot"
        ),
    }
    selection["status"] = (
        "signed_snapshot_and_exact_package_closure_resolved_no_image_claim"
    )
    write_json(path, selection)


def d0r02_checkpoint(lock: dict[str, Any]) -> dict[str, Any]:
    return {
        "evidence": "docs/evidence/2026-08-29-d0r02-debian-snapshot.md",
        "id": "D0R-02",
        "lock": str(LOCK_RELATIVE),
        "lock_file_sha256": EXPECTED_LOCK_SHA256,
        "package_count": lock["resolved_package_count"],
        "package_set_sha256": lock["package_set_sha256"],
        "snapshot_timestamp": lock["snapshot_timestamp"],
        "status": (
            "INPUT_VALIDATED_SIGNED_SNAPSHOT_AND_FULL_PACKAGE_CLOSURE_NO_IMAGE"
        ),
        "validated_source_head": QUALIFYING_SOURCE_HEAD,
        "workflow_artifact_id": QUALIFYING_ARTIFACT_ID,
        "workflow_artifact_sha256": QUALIFYING_ARTIFACT_SHA256,
        "workflow_run_id": QUALIFYING_RUN_ID,
    }


def promote_repository_state(root: Path, lock: dict[str, Any]) -> None:
    path = root / "manifests/repository-state.json"
    state = read_json(path)
    completed = [item for item in state.get("completed_work_packages", []) if item != "D0R-02"]
    insert_at = completed.index("D0R-01") + 1 if "D0R-01" in completed else 0
    completed.insert(insert_at, "D0R-02")
    state["completed_work_packages"] = completed
    state["partial_work_packages"] = [
        item for item in state.get("partial_work_packages", []) if item != "D0R-02"
    ]
    state["input_validated_work_packages"] = [d0r02_checkpoint(lock)]
    state["implementation_stage"] = "D0R02_INPUT_VALIDATED_D0C05_HOST_VALIDATED"
    write_json(path, state)


def promote_docs_manifest(root: Path, lock: dict[str, Any]) -> None:
    path = root / "docs/MANIFEST.json"
    manifest = read_json(path)
    manifest["debian_signed_snapshot_resolved"] = True
    manifest["debian_snapshot_lock"] = "../manifests/debian-snapshot.lock.v1.json"
    manifest["debian_snapshot_requirements"] = (
        "../manifests/debian-snapshot.requirements.v1.json"
    )
    manifest["debian_image_built"] = False
    existing = [
        item
        for item in manifest.get("implementation_checkpoints", [])
        if isinstance(item, dict) and item.get("id") != "TOS-D0R-02"
    ]
    docs_checkpoint = {
        "evidence": "evidence/2026-08-29-d0r02-debian-snapshot.md",
        "id": "TOS-D0R-02",
        "machine_evidence": "../manifests/debian-snapshot.lock.v1.json",
        "package_count": lock["resolved_package_count"],
        "package_set_sha256": lock["package_set_sha256"],
        "snapshot_timestamp": lock["snapshot_timestamp"],
        "status": (
            "INPUT_VALIDATED_SIGNED_SNAPSHOT_AND_FULL_PACKAGE_CLOSURE_NO_IMAGE"
        ),
        "validated_source_head": QUALIFYING_SOURCE_HEAD,
        "workflow_run_id": QUALIFYING_RUN_ID,
    }
    manifest["implementation_checkpoints"] = [docs_checkpoint, *existing]
    manifest["implementation_stage"] = "D0R02_INPUT_VALIDATED_D0C05_HOST_VALIDATED"
    manifest["status"] = "INPUT_VALIDATED_AND_IMPLEMENTATION_HOST_VALIDATED"
    write_json(path, manifest)


def promote_plan(root: Path) -> None:
    plan = root / "docs/DESKTOP_PLAN-2026-08-28-d5.md"
    replace_once_or_already(
        plan,
        "- Rust 1.93 workspace, exact dependency closure, CI, and claim validation;\n",
        "- Rust 1.93 workspace, exact dependency closure, CI, and claim validation;\n"
        "- signed Debian snapshot `20260828T000000Z`, three exact `InRelease` "
        "digests, and a 319-package closure with canonical package-set digest;\n",
    )
    replace_once_or_already(
        plan,
        "| `D0R` repository/reproducibility | foundation implemented; signed Debian input closure partial | resolve signed snapshot, archive keys, package closure, and deterministic builder for D1 |",
        "| `D0R` repository/reproducibility | signed snapshot and exact package closure input validated | consume the committed lock in a deterministic D1 builder |",
    )
    replace_once_or_already(
        plan,
        "3. `D0R-02` / `D1-01`: resolve signed Debian inputs, build two deterministic\n"
        "   image candidates, boot QEMU into systemd/Wayland, and run the D0C-05 PID 1\n"
        "   activation corpus in a test-only image while keeping the product image\n"
        "   default-disabled.\n",
        "3. `D1-01`: consume the committed D0R-02 signed Debian lock, build two\n"
        "   deterministic image candidates, boot QEMU into systemd/Wayland, and run\n"
        "   the D0C-05 PID 1 activation corpus in a test-only image while keeping the\n"
        "   product image default-disabled.\n",
    )

    annex = root / "docs/plan/WORK_PACKAGES_AND_GATES.md"
    old_block = """#### `D0R-02` Toolchain and input selections — IMPLEMENTED/PARTIAL

- lock Rust 1.93.0;
- select Debian 13/trixie amd64;
- select Servo commit `670ae8a70801b162e186f81cbb5bdd2d59c39108`;
- record mobile reference commit and dependency exclusions.

**Remaining gate:** Debian snapshot timestamp, signed `InRelease` digests,
archive-key fingerprints, exact package closure, and package-set digest must be
resolved before D1 promotion. A point-release label alone is not an input lock.
"""
    new_block = """#### `D0R-02` Toolchain and input selections — INPUT VALIDATED

- lock Rust 1.93.0;
- select Debian 13/trixie amd64;
- select Servo commit `670ae8a70801b162e186f81cbb5bdd2d59c39108`;
- record mobile reference commit and dependency exclusions;
- lock snapshot `20260828T000000Z`, three signed `InRelease` objects, pinned
  Debian 13 primary trust roots, and the complete exact package closure.

**Demonstrated exit:** source head
`6825f9bd4bd012212559d187315bca285a6ae3d2` passed workflow run
`33196743127`; `manifests/debian-snapshot.lock.v1.json` records 319 downloaded
and metadata-verified packages with package-set SHA-256
`89918a968afafdbabe03e43794565cb1dc936f3f24a09ec81030be4a4085333a`.
The lock explicitly claims no rootfs, image, QEMU, Wayland, Secure Boot or
product readiness. D1-01 remains the next gate.
"""
    replace_once_or_already(annex, old_block, new_block)
    replace_once_or_already(
        annex,
        "3. Resolve `D0R-02` signed Debian inputs and execute `D1-01`, including the\n"
        "   D0C-05 PID 1 activation corpus in a test-only image.\n",
        "3. Execute `D1-01` from the committed D0R-02 signed Debian lock, including\n"
        "   the D0C-05 PID 1 activation corpus in a test-only image.\n",
    )


def promote_text_documents(root: Path, lock: dict[str, Any]) -> None:
    inrelease = {item["id"]: item for item in lock["inrelease"]}
    write_text(
        root / "docs/evidence/2026-08-29-d0r02-debian-snapshot.md",
        f"""# D0R-02 signed Debian snapshot evidence

**Date:** 2026-08-29  
**Requested snapshot:** `{lock['snapshot_timestamp']}`  
**Architecture:** `{lock['architecture']}`  
**Status:** `{lock['status']}`

## Exact qualifying execution

Source head `{QUALIFYING_SOURCE_HEAD}` passed the permanent
`debian-snapshot-lock` workflow in run `{QUALIFYING_RUN_ID}`. The uploaded
evidence was artifact `{QUALIFYING_ARTIFACT_ID}`, named
`{QUALIFYING_ARTIFACT_NAME}`, with ZIP SHA-256
`{QUALIFYING_ARTIFACT_SHA256}`.

The canonical machine lock is committed at `{LOCK_RELATIVE}`. Its exact file
SHA-256 is `{EXPECTED_LOCK_SHA256}`. The permanent workflow regenerates that
lock and requires a byte-for-byte match before the checkpoint can remain green.

## Signed archive inputs

| Archive | Suite | InRelease SHA-256 | Accepted valid primary key |
| --- | --- | --- | --- |
| Debian | `trixie` | `{inrelease['debian']['sha256']}` | `04B54C3CDCA79751B16BC6B5225629DF75B188BD`, `41587F7DB8C774BCCF131416762F67A0B2C39DE4` |
| Debian updates | `trixie-updates` | `{inrelease['debian-updates']['sha256']}` | `04B54C3CDCA79751B16BC6B5225629DF75B188BD` |
| Debian security | `trixie-security` | `{inrelease['debian-security']['sha256']}` | `5E04A1E3223A19A20706E20F9904613D4CCE68C6` |

The minimal keyring SHA-256 is `{lock['archive_keyring']['sha256']}`. Additional
unknown co-signers are recorded but cannot replace the required valid signature
from an accepted pinned primary key. Bad, expired, revoked, missing-data and
internal signature failure states remain fatal.

## Exact package closure

APT resolved from an empty isolated dpkg status database with recommends
disabled and unauthenticated/insecure repositories forbidden. It selected and
downloaded `{lock['resolved_package_count']}` packages. Every `.deb` byte length
and SHA-256 matched signed APT metadata. The canonical sorted package-set
SHA-256 is `{lock['package_set_sha256']}`.

## Claim ceiling

This checkpoint proves signed immutable Debian inputs and their complete amd64
package closure only. It did not create a root filesystem or disk image, did
not boot QEMU, did not start systemd or Wayland, did not enable Secure Boot,
and does not claim product or release readiness. The next gate is `D1-01`.
""",
    )
    write_text(
        root / "docs/architecture/DEBIAN_SNAPSHOT_LOCK.md",
        f"""# Signed Debian snapshot lock

**Work package:** `TOS-D0R-02`  
**Architecture:** `{lock['architecture']}`  
**Snapshot:** `{lock['snapshot_timestamp']}`  
**Status:** input validated  
**Claim class:** signed inputs and package closure only

## Trust and resolution model

The D1 image may not resolve packages from a rolling mirror. For each frozen
source, the gate downloads the exact `InRelease`, requires a valid signature
from an archive-specific pinned Debian 13 primary fingerprint, records all
valid and unknown co-signers, and hashes the exact signed file. Bad, expired,
revoked, missing-data and internal verification states are fatal. An unknown
additional co-signer can never substitute for a required accepted signature.

Package resolution runs against an empty isolated dpkg status database with
`--no-install-recommends`. Every selected package is downloaded and its byte
length and SHA-256 are compared with signed APT metadata.

## Canonical repository lock

`{LOCK_RELATIVE}` is the only D1 package input lock. It contains three exact
signed `InRelease` records, the minimal Debian 13 trust roots, and all
`{lock['resolved_package_count']}` selected packages. The package-set SHA-256 is
`{lock['package_set_sha256']}`.

The permanent workflow regenerates the lock and requires a byte-for-byte match.
The offline validator independently recomputes the package-set digest and
checks the lock, selection, documentation manifest and repository state.

## Promotion boundary

D0R-02 is input validated. It does not create a rootfs or image and does not
boot QEMU. D1-01 must consume this lock and prove reproducible construction,
systemd/Wayland boot, and the test-only D0C-05 PID 1 activation corpus while
the product image remains default-disabled.
""",
    )
    write_text(
        root / "docs/plan/D0R02_EXECUTION_CHECKPOINT-2026-08-29.md",
        f"""# D0R-02 execution checkpoint — signed Debian input closure

**Plan revision:** `2026-08-28-d5`  
**Work package:** `D0R-02`  
**Checkpoint status:** `INPUT_VALIDATED`  
**Next gate:** `D1-01`

Exact source head `{QUALIFYING_SOURCE_HEAD}` passed workflow run
`{QUALIFYING_RUN_ID}`. The generated lock was promoted without editing to
`{LOCK_RELATIVE}` and is regenerated and compared byte-for-byte by the
permanent workflow.

Observable exit: snapshot `{lock['snapshot_timestamp']}`; three pinned Debian
13 primary trust roots; three exact signed `InRelease` digests; empty-dpkg,
no-recommends, fail-closed APT resolution; `{lock['resolved_package_count']}`
downloaded and metadata-verified packages; package-set SHA-256
`{lock['package_set_sha256']}`; and all image/runtime/release claims false.

This closes only D0R-02. D1-01 remains responsible for deterministic rootfs and
image construction, independent rebuild equality, QEMU/systemd/Wayland evidence
and live test-only socket activation.
""",
    )
    write_text(
        root / "manifests/README.md",
        """# Product manifests

These files record selected and locked product inputs and explicit blockers.
An input lock does not prove a built or booted product; claim ceilings remain
explicit and fail closed.

- `repository-state.json` — implementation, validation and non-claim status
- `servo.lock.json` — pinned Servo compatibility-spike commit
- `rust-toolchain.lock.json` — Rust compiler/tool components
- `debian-base.selection.json` — selected Debian base and canonical lock pointer
- `debian-snapshot.requirements.v1.json` — signed snapshot and resolver policy
- `debian-snapshot.lock.v1.json` — exact signed InRelease and package closure
- `product-boundary.json` — desktop/mobile dependency firewall
""",
    )


def promote_current_state(root: Path, lock: dict[str, Any]) -> None:
    write_text(
        root / "docs/CURRENT_STATE.md",
        f"""# TrillionniumOS Desktop — current state

**Updated:** 2026-08-29  
**Canonical plan:** `2026-08-28-d5`  
**Repository mode:** `FULL_PRODUCT_REPOSITORY`  
**Implementation stage:** `D0R02_INPUT_VALIDATED_D0C05_HOST_VALIDATED`

## Implemented and demonstrated

The D0 foundation includes the Rust workspace, layered revisions, deterministic
Agent/human arbitration, synthetic trusted origins, browser contracts, exact
Cargo dependency closure, fail-closed product/evidence validation, and a signed
immutable Debian package input closure.

The local Agent path remains host-validated through D0C-05:

```text
already-connected AF_UNIX stream
  -> SO_PEERCRED + nonce + sequence + digest transport
  -> bounded canonical Browser API codec
  -> exactly-one request-bound AgentPort handler
  -> default-disabled systemd socket custody
  -> pidfd/procfs/cgroup/unit peer attestation
```

The socket remains closed by default: its preset disables it, the required
`/etc/hepta/enable-agent-port` marker is not shipped, and no product listener is
claimed.

## D0R-02 signed immutable Debian inputs

Source head `{QUALIFYING_SOURCE_HEAD}` passed workflow run
`{QUALIFYING_RUN_ID}`. `{LOCK_RELATIVE}` proves snapshot
`{lock['snapshot_timestamp']}`, three exact signed `InRelease` records,
`{lock['resolved_package_count']}` downloaded and metadata-verified packages,
and package-set SHA-256 `{lock['package_set_sha256']}`. All rootfs, image, QEMU,
Wayland, Secure Boot and product-ready claims remain false.

## Existing exact-head host validation

- D0C-02: head `786debc12aa8d790b231397c1a3341fbf89de080`, run `33167838644`.
- D0C-03: head `4cfebbe6a40ebbec32d9d1bcbfca1d513b510ebb`, run `33176689873`.
- D0C-04: head `5abd71db79b75e400c1c1d7cb0eac85a68041cae`, run `33179346462`.
- D0C-05: head `7be7121b1d2593a0e708ec9ade189ef84ab245da`, permanent custody,
  repository-wide CI and codec/reference regression evidence committed under
  `docs/evidence/generated/`.

## Not implemented or claimed

- No deterministic rootfs or disk image has been built from the committed lock.
- QEMU PID 1 activation, live authorized/unauthorized socket tests, teardown,
  recovery and the supervised Wayland placeholder are not demonstrated.
- No product AgentPort listener is enabled.
- No BrowserActor dispatch or Servo runtime exists in the demonstrated product.
- No visible first frame, native input/IME or headed trusted workspace is
  claimed.
- No external navigation, capability, credential use or web effect is
  authorized.
- No signed app runtime, Secure Boot, update/rollback, beta or release claim
  exists.

## Active next work

1. Complete D0A-01 against Servo pin
   `670ae8a70801b162e186f81cbb5bdd2d59c39108` and Servo's own toolchain.
2. Execute D1-01 from the committed Debian lock: build two normalized
   candidates, prove equality, boot QEMU/systemd/Wayland, and run the D0C-05
   PID 1 activation corpus in a test-only image while keeping the product image
   default-disabled.
3. Complete D0A-02/D2 trusted workspace composition, one Servo content surface,
   local first frame, native pointer/keyboard/IME, popup refusal and recovery.
4. Implement D0C-06 durable receipts before BrowserActor operation claims.
5. Keep external credentials, capabilities, navigation effects, update
   authority and release claims closed until their explicit gates pass.
""",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generated-lock", required=True, type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    raw = args.generated_lock.read_bytes()
    lock = json.loads(raw.decode("utf-8"))
    if not isinstance(lock, dict):
        raise RuntimeError("generated lock must contain a JSON object")
    validate_generated_lock(raw, lock)

    canonical = root / LOCK_RELATIVE
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_bytes(raw)
    promote_selection(root, lock)
    promote_repository_state(root, lock)
    promote_docs_manifest(root, lock)
    promote_text_documents(root, lock)
    promote_current_state(root, lock)
    promote_plan(root)
    print(
        "promoted canonical D0R-02 lock: "
        f"sha256={EXPECTED_LOCK_SHA256} packages={lock['resolved_package_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
