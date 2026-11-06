#!/usr/bin/env python3
"""Offline derivation from preserved receipts and primary-source observations.

Does not resolve DNS, download, execute a tool, inspect Android, or authorize a retry.
Actual JSON is decoded by Python so integer identities are never rounded by JS.
"""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent


def read(rel, expected_sha=None):
    path = PROJECT / rel
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if expected_sha is not None:
        assert sha == expected_sha, (rel, sha, expected_sha)
    return json.loads(raw), {"path": rel, "bytes": len(raw), "sha256": sha}


def write_new(name, value):
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    path = HERE / name
    if path.exists():
        assert path.read_bytes() == raw, ("FROZEN_OUTPUT_DIFFERS", str(path))
    else:
        with path.open("xb") as stream:
            stream.write(raw)
    return {"path": str(path.relative_to(PROJECT)), "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest()}


matrix, matrix_ref = read("reference/remaining34-source-actions.json")
apps = {app["package"]: app for app in matrix["apps"]}
s34, s34_ref = read(
    "official_source_scripts/s34_zbj_tail/actual-r1/com.zhubajie.client-result.raw.json",
    "c49b3c374226329c92810d11bacee29c75023c26bf648bf5c4a6ebf7ea741135")
failure, failure_ref = read(
    "official_source_scripts/s34_zbj_tail/actual-r1/range-0003.raw.json",
    "a92c797bdd1d9471842afa76c3d2872249d78b42286997b393fe191949436a6b")
terminal, terminal_ref = read(
    "official_source_scripts/s34_zbj_tail/actual-r1/terminal.raw.json",
    "e10d132f8089f20add7a403ff05bd31620fd785ab8f7db934817bdae797ba239")
rail_failures = []
for name, expected in [
    ("rail-0000.json", "d23ad050f6515582763759d5d2e51907e73f7e293faa4ae44fbf589a71788c94"),
    ("rail-0001.json", "3e85886f3fd8b909f8f1826772d505b147d0a2392503c44d17cf069c6cb9306f"),
]:
    item, ref = read("reference/official-s24-s33-restored/s24/" + name, expected)
    assert item["returncode"] == 35
    assert item["curl"]["http_code"] == 0 and item["curl"]["size_download"] == 0
    rail_failures.append({"evidence": ref, "returncode": item["returncode"],
                          "curl": item["curl"], "start": item["start"], "end": item["end"]})

assert s34["status"] == "SEGMENTED_TRANSFER_FAILED"
assert s34["segment_counts"] == {"COMPLETE": 3, "FAILED": 1,
                                    "SKIPPED_AFTER_OTHER_RANGE_FAILURE": 37}
assert s34["etag_chain"] == {"values": [], "all_observations_equal": True,
                               "server_supplied_validator": False}
assert failure["returncode"] == 6 and failure["curl"]["http_code"] == 0
assert failure["partial_bytes"] == 0 and failure["curl"]["size_download"] == 0
assert failure["request_attempts"] == 1 and failure["automatic_retries"] == 0
assert failure["joined"] is True and failure["pidfd_closed"] is True
assert failure["pidfd_exit_observed"] is True and failure["outcome_unknown"] is False

successful = []
next_start = s34["prefix_bytes"]
for index in range(3):
    receipt = s34["segment_receipts"][index]
    span = s34["declared_ranges"][index]
    assert receipt["index"] == index and receipt["status"] == "COMPLETE"
    assert span["index"] == index and span["start"] == next_start
    assert span["end"] - span["start"] + 1 == 1048576
    successful.append({**span, "bytes": 1048576, "receipt": receipt["receipt"],
                       "full_receipt_read_in_this_research": False})
    next_start = span["end"] + 1
assert next_start == failure["start"] == 127516672
remaining = s34["total_bytes"] - next_start
assert remaining == 39356950
ranges = []
for index, start in enumerate(range(next_start, s34["total_bytes"], 1048576)):
    end = min(start + 1048576, s34["total_bytes"]) - 1
    ranges.append({"index": index, "start": start, "end": end, "bytes": end-start+1})
assert len(ranges) == 38 and sum(row["bytes"] for row in ranges) == remaining
assert ranges[-1]["end"] == 166873621

observed_360_url = (
    "https://s.shouji.qihucdn.com/261009/9b8bc092373e8f09d56861322b8ce1c9/"
    "com.zhubajie.client_370.apk?en=curpage%3Dopenbox_wap_detail%26exp%3D1794571796"
    "%26from%3Dopenbox_mintf_getAppInfoByIds%26m2%3D%26ts%3D1793966996"
    "%26tok%3D5969849da6d36e613200ad4a0953dfdc%26v%3D%26f%3Dz.apk")

sources = [
    {"id": "rail_vendor", "url": "https://kyfw.12306.cn/otn/appDownload/init",
     "web_ref": "turn115view0", "kind": "publisher", "observed": "Official Android download link; no version published in parsed page."},
    {"id": "rail_vendor_redirect", "url": "https://dynamic.12306.cn/otn/appDownload/androiddownload",
     "web_ref": "turn116view2", "kind": "publisher",
     "observed_final_url": "https://mobile.12306.cn/otsmobile/h5/otsbussiness/downloadapp/downloadapp.html",
     "observed": "Normal publisher redirect; web reader returned zero readable lines. No current config or APK acquired."},
    {"id": "rail_xiaomi", "url": "https://app.mi.com/details?id=com.MobileTicket",
     "web_ref": "turn115search0", "kind": "official_store",
     "version_name": "5.9.6.8", "updated": "2026-07-15", "observed": "Desktop page displays maintenance; metadata is not an APK."},
    {"id": "rail_xiaomi_mobile", "url": "https://m.app.mi.com/details?id=com.MobileTicket",
     "web_ref": "turn116view1", "kind": "official_store",
     "version_name": "5.9.6.8", "updated": "2026-07-15",
     "observed": "Free download text appears, but this read exposed no APK href."},
    {"id": "rail_sogou", "url": "https://as.sogou.com/app/apkdetail?anchor=appDetail&cid=42&docid=-6087132986774887796&pid=34",
     "web_ref": "turn117view0", "kind": "official_store",
     "version_name": "5.9.6.8", "updated": "2026-07-15", "delivery_source_published": "应用宝",
     "observed": "Not evidence of an independent CDN or a new complete delivery; no APK href exposed."},
    {"id": "rail_tencent", "url": "https://sj.qq.com/appdetail/com.MobileTicket",
     "web_ref": "turn117view1", "kind": "official_store",
     "displayed_version_literal": "V5.9.6", "updated": "2026-07-15",
     "observed": "Public store page; no new APK download URL exposed by this read."},
    {"id": "rail_360_older", "url": "https://app.so.com/detail/index?id=903638&pname=com.MobileTicket",
     "web_ref": "turn116search0", "kind": "official_store",
     "version_name": "5.7.0.8", "updated": "2023-08-28", "use_as_upgrade": False},
    {"id": "rail_play_different_package", "url": "https://play.google.com/store/apps/details?hl=zh&id=com.chinarailway.globalticketing",
     "web_ref": "turn116search5", "kind": "official_store", "package": "com.chinarailway.globalticketing",
     "use_as_com_MobileTicket_upgrade": False, "observed": "Different package; no substitution or Play delivery bypass."},
    {"id": "zbj_vendor", "url": "https://app.zbj.com/bz/pc/", "web_ref": "turn116view1",
     "actual_open_web_ref": "turn116view0", "kind": "publisher",
     "direct_open_version_name": "8.5.60", "direct_open_updated": "2024-2-1",
     "search_cache_version_name": "9.5.00", "search_cache_updated": "2026-07-16",
     "observed": "Conflicting cache and direct page; neither proves current deliverable version."},
    {"id": "zbj_vendor_download", "url": "https://app.zbj.com/bz/pc/download/",
     "web_ref": "turn118view1", "kind": "publisher",
     "observed": "QR/download presentation; no current complete APK link exposed in this read."},
    {"id": "zbj_360", "url": "https://app.so.com/detail/index?id=238882&pt=oauth",
     "web_ref": "turn115view1", "kind": "official_store", "version_name": "9.5.20", "updated": "2026-10-09",
     "observed_download_url": observed_360_url, "download_web_ref": "turn116view3",
     "observed": "Normal download click reached application/vnd.android.package-archive; web reader rejected binary content. No bytes, complete length, current ETag, signature or Pocket4 reachability were acquired."},
    {"id": "zbj_tencent", "url": "https://sj.qq.com/appdetail/com.zhubajie.client",
     "web_ref": "turn117view2", "kind": "official_store", "version_name": "9.5.20", "updated": "2026-10-09",
     "observed": "Current matching metadata; no distinct complete APK URL exposed by this read."},
    {"id": "oppo_store", "url": "https://store.oppomobile.com/index.html",
     "web_ref": "turn119search0", "kind": "official_store",
     "observed": "Official store client entry only; no package-specific delivery or authentication state established."},
]
# Keep the vendor citation unambiguous; the extra direct-open field above records
# that search cache and direct reads were different observations.
sources[8]["web_ref"] = "turn116view0"

receipt_query = {
    "schema": "pocket4.fixed_public_artifact_receipt_read_plan.v1",
    "state": "LOCAL_PLAN_NOT_EXECUTED",
    "reason": "Read the three actual S34 COMPLETE receipts before deriving exact reusable segment paths and byte identities.",
    "authority": [s34_ref, failure_ref, terminal_ref],
    "operation": "file_info then version-bound binary_read; no process submission",
    "files": [row["receipt"] for row in successful],
    "aggregate_expected_bytes": sum(row["receipt"]["bytes"] for row in successful),
    "max_bytes_per_file": 4096,
    "checks": ["exact fixed path", "regular no-follow file", "actual size equals expected size",
               "bind binary_read to file_info version", "save raw tool payload before parsing",
               "Python validates original byte length and full SHA-256", "no automatic retry or alternate path"],
    "remote_processes": 0, "Android_reads": 0, "Main_lock_or_fds": 0,
}
query_ref = write_new("bounded-receipt-read-plan.json", receipt_query)

proposal = {
    "schema": "pocket4.zbj_explicit_continuation_proposal.v1",
    "state": "CONDITIONAL_DRAFT_NOT_SEALED_NOT_EXECUTED",
    "new_executable_or_process_request_prepared": False,
    "package": "com.zhubajie.client",
    "base_source": "official_source_scripts/s34_zbj_tail/resume_zbj_tail_s34_once.py",
    "settled_previous_job": "1a1b19cedcf-fc05-79de",
    "previous_result": s34_ref, "previous_failure": failure_ref,
    "new_information": ["Current official360 page still exposes the same APK path.",
                        "S34 succeeded for three 1MiB ranges, then failed only at normal DNS resolution with zero bytes and HTTP0.",
                        "No HTTP refusal or retry was observed in that failed transfer; this does not establish current host DNS recovery."],
    "blocking_inputs_before_packet_seal": [
        "Read and pin all three COMPLETE range receipts using bounded-receipt-read-plan.json.",
        "Bind each complete range body/header/metrics path and identity from those receipts; do not invent the body hashes.",
        "Define a single bounded normal system-resolver admission for the exact existing CDN host; a failed result settles the attempt without a download.",
        "Root reviews one explicit new attempt and a unique staging root/key. This proposal itself authorizes neither a retry nor a remote process."],
    "download_url_candidate": s34["url"],
    "alternative_currently_observed_store_url": observed_360_url,
    "url_choice": "Prefer unchanged original URL; a query-token change is not silently substituted. A changed URL requires separate explicit provenance and entity review.",
    "expected_total_bytes": s34["total_bytes"],
    "original_verified_prefix_bytes": s34["prefix_bytes"],
    "original_verified_prefix_sha256": s34["prefix_sha256"],
    "additional_complete_segments": successful,
    "conditional_reusable_prefix_bytes": next_start,
    "new_combined_prefix_sha256": None,
    "new_combined_prefix_revalidated_on_host": False,
    "remaining_bytes": remaining,
    "declared_ranges": ranges,
    "max_connections": 1, "max_parallel_transfers": 1,
    "requests_per_range": 1, "automatic_retries": 0,
    "proposed_total_deadline_seconds": 1800,
    "client_contract": "Inherit existing curl UA Mozilla/5.0, normal certificate verification, HTTPS only, exact206 Content-Range, total length and per-range byte count; no --resolve, custom DNS, IP substitution, proxy changes, TLS/UA changes or mirror substitution.",
    "stop_conditions": ["DNS/TLS/HTTP/partial-body/shape failure", "HTTP403", "HTTP429", "Retry-After", "identity or hash mismatch", "deadline exhaustion", "unknown child outcome"],
    "etag_status": s34["etag_chain"],
    "etag_interpretation": "No server validator was supplied. Empty equal values are not an entity-continuity proof. Do not send a fabricated If-Range validator or count ETag continuity as PASS.",
    "final_candidate_gate": [
        "All prior and newly complete body/header/metrics receipts remain byte-exact and are revalidated; failed or empty partials are never reused.",
        "Complete166873622-byte APK is assembled in a new staging artifact and full SHA256 is recorded.",
        "Do not infer MD5 from the URL path; metadata_md5 remains null unless separately published by an authoritative source.",
        "A subsequent separately reviewed existing verifier must pass full-APK signature verification with a v2/v3 whole-APK scheme and the expected vendor signer; no concatenated candidate is installable before it passes.",
        "Actual manifest must be com.zhubajie.client, versionCode370/versionName9.5.20 or separately reviewed newer metadata, and ABI/minSdk compatible with current qualified runtime.",
        "Fresh installed identity and signer lineage must be read under the current guard before any separately authorized upgrade."],
    "historical_expected_signer_sha256": apps["com.zhubajie.client"]["current_bound_identity"]["package_manager_certificate_sha256"],
    "Android_reads": 0, "Main_lock_or_fds": 0, "installs": 0,
    "complete_candidate_obtained": False, "signature_verified": False,
    "production_ready": False, "cleanup_eligible": False,
}
proposal_ref = write_new("zbj-conditional-continuation-plan.json", proposal)

findings = {
    "schema": "pocket4.rail_zbj_official_delivery_research.v1",
    "as_of_utc_date": "2026-11-06",
    "state": "RESEARCH_AND_CONDITIONAL_PROPOSAL_NOT_EXECUTED",
    "prior_matrix": matrix_ref, "primary_source_observations": sources,
    "scope": ["com.MobileTicket", "com.zhubajie.client"],
    "apps": [
        {"package": "com.MobileTicket", "status": "BLOCKED_NO_NEW_COMPLETE_OFFICIAL_DELIVERY",
         "historical_bound_identity": apps["com.MobileTicket"]["current_bound_identity"],
         "existing_candidate": apps["com.MobileTicket"]["official_source"],
         "actual_old_tls_failures": rail_failures,
         "current_primary_metadata_candidate": "5.9.6.8",
         "new_complete_APK_or_independent_download_url": None,
         "next_minimum_action": "Use a newly published ordinary official same-package delivery, or a normally available official store client. No store login or installation is presumed authorized by this research. Do not retry the unchanged failed Tencent endpoint without new cause-specific evidence.",
         "rejected_substitutions": ["Older3605.7.0.8", "EarlierBaidu5.9.0.8/403", "GooglePlay com.chinarailway.globalticketing", "Third-party APK mirrors", "Cloud browser URL-policy workaround"],
         "original_normal_vendor_config": "Historical5.9.4.5; current config not reacquired in this research.",
         "production_ready": False, "cleanup_eligible": False},
        {"package": "com.zhubajie.client", "status": "BLOCKED_PARTIAL_ONLY_WITH_FINITE_CONDITIONAL_RESUME_PATH",
         "historical_bound_identity": apps["com.zhubajie.client"]["current_bound_identity"],
         "current_primary_metadata_candidate": "9.5.20",
         "actual_s34_result": s34_ref, "actual_terminal": terminal_ref,
         "actual_s34_failure": failure_ref,
         "failure_reason": "curl6: Could not resolve host: s.shouji.qihucdn.com; HTTP0 and zero body/header bytes.",
         "actual_s34_new_complete_ranges": successful,
         "conditional_total_contiguous_bytes": next_start,
         "remaining_bytes": remaining,
         "server_validator_supplied": False,
         "actual_owned_processes": s34["owned_curl_processes"],
         "actual_prior_file_descriptors": s34["prior_file_descriptors"],
         "bounded_read_plan": query_ref, "conditional_continuation_plan": proposal_ref,
         "new_complete_APK": None, "signature_verified": False,
         "production_ready": False, "cleanup_eligible": False},
    ],
    "limits": ["Public metadata is not an artifact or proof of compatibility.",
               "Web service CDN response is not Pocket4 DNS/TLS evidence.",
               "Historical installed identities are not fresh runtime observations.",
               "No vendor-global latest-version guarantee is inferred from store observations.",
               "The original per-range successes and the overall FAILED result coexist; no failure is relabelled as success."],
    "new_remote_processes": 0, "Android_reads": 0, "Main_lock_or_fds": 0,
    "new_APK_bytes_downloaded": 0, "installs": 0, "permission_changes": 0,
    "all_launcher_upgrade_complete": False, "production_ready": False,
    "cleanup_eligible": False,
}
findings_ref = write_new("findings.json", findings)

files = []
for path in sorted(HERE.iterdir()):
    if path.is_file() and path.name != "index.json":
        raw = path.read_bytes()
        files.append({"path": str(path.relative_to(PROJECT)), "bytes": len(raw),
                      "sha256": hashlib.sha256(raw).hexdigest()})
index_ref = write_new("index.json", {
    "schema": "pocket4.source_research_archive_index.v1",
    "base_checkpoint": "0138f236da62eb85d2b7b136f47efaf00104ab9e",
    "files": files, "file_count": len(files),
    "total_bytes": sum(row["bytes"] for row in files),
    "APK_or_private_UI_copied": False, "old_files_modified_or_deleted": False,
    "actual_remote_or_Android_execution": False,
})
print(json.dumps({"findings": findings_ref, "receipt_query": query_ref,
                  "continuation_proposal": proposal_ref, "index": index_ref}, indent=2))
