#!/usr/bin/env python3
"""Build a compact, evidence-linked current Launcher inventory; no target calls."""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
INPUTS = {}


def read(name, expected_sha=None):
    raw = (PROJECT / name).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha is not None:
        assert digest == expected_sha, name
    INPUTS[name] = {"path": name, "bytes": len(raw), "sha256": digest}
    return json.loads(raw)


def save(name, value):
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    (HERE / name).write_bytes(raw)
    return {"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def main():
    matrix_path = "audit_matrix_r1/snapshots/c79b953103d9d432fcbe/EVIDENCE_MATRIX.json"
    old = read(matrix_path)
    coverage_path = "successor_audit_requests/revisions/b13-linked-coverage-r1/COVERAGE.actual.json"
    coverage = read(coverage_path)
    assert coverage["ok"] and coverage["observed_packages"] == 45 and coverage["observed_APKs"] == 85
    discovery_path = "successor_audit_requests/native46_discovery_r1/actual/artifact.original.json"
    discovery = read(discovery_path, "69482778466e03dceff2defc85fb8f68880c360a3f112e129561a8fd5e6e5400")
    joint = read("successor_audit_requests/native46_discovery_r1/actual/root-validation.actual.json")
    assert joint["status"] == "PASS_DISCOVERY_WITH_NO_SCOPE_PROMOTION"
    assert discovery["ok"] and discovery["current_scope_47_unchanged"] and len(discovery["installed_packages"]) == 206
    components = discovery["MAIN_LAUNCHER_components"]
    assert len(components) == len({r["package"] for r in components}) == 46
    current_pm = {r["package"]: r for r in discovery["installed_packages"]}
    audits = {r["package"]: r for r in coverage["packages"]}
    previous = {r["package"]: r for r in old["apps"]}
    beike_path = "successor_audit_requests/beike_permission_pilot_r1/EFFECTIVE_PERMISSION_OBSERVATION.derived.json"
    fcitx_path = "successor_audit_requests/effective_permissions_private_readback_r1/batch-01-p00/actual-public/PERMISSIONS.derived.json"
    microg_path = "successor_audit_requests/effective_permissions_microg_parser_r1/actual/PERMISSIONS.derived.json"
    effective = {r["package"]: (r, name) for name in (beike_path, fcitx_path, microg_path) for r in [read(name)]}
    beike_diag_path = "successor_qa/search_click_failure_reader_r1/actual-public/stdout.original.json"
    beike_diag = read(beike_diag_path, "c6b1396ac512fe5730497a2de75642cce3d6c0c24bccbc5a9a83a41b37002e9b")
    assert beike_diag["collection_completed"] and beike_diag["diagnosis_completed"]
    memory_path = "framework_provider_repair/normal06/current470-authorization-r1/memory-observation-after-native46-r1/actual/summary.derived.json"
    memory = read(memory_path)
    international_delivery_path = "official_source_scripts/s44_international_delivery_metadata/international14-delivery-evidence.json"
    international_delivery = read(international_delivery_path)
    marriott_delivery_path = "official_source_scripts/s44_international_delivery_metadata/candidate-r1/actual/root-validation.actual.json"
    marriott_delivery = read(marriott_delivery_path)
    old_8 = {r["package"] for r in old["apps"] if r["original_eight"]}
    assert len(old_8) == 8
    rows = []
    for component in sorted(components, key=lambda x: x["package"]):
        package = component["package"]
        prior = previous.get(package)
        audit = audits.get(package)
        row = {
            "package": package, "component": component["component"], "original_eight": package in old_8,
            "label_reference": prior["label_reference"] if prior else None,
            "label_is_fresh_observation": False,
            "PM": {**current_pm[package], "source": discovery_path},
            "version_name": audit["declared_version_name"] if audit else None,
            "version_name_evidence": "APK_MANIFEST" if audit else "UNKNOWN_APK_MANIFEST_NOT_YET_PARSED",
            "declared_version_code": audit["declared_version_code"] if audit else None,
            "APK_audit": {"state": "LINKED_NORMAL_SIGNATURE_AND_MANIFEST_VERIFIED" if audit else "IDENTITY_ONLY_SIGNATURE_PENDING",
                          "source": coverage_path if audit else discovery_path,
                          "details": audit if audit else discovery["new_package_identity"]},
            "classification": prior["classification"] if prior else "OWNER_AND_SOURCE_UNKNOWN",
            "upgrade": prior["upgrade"] if prior else {"state": "NEWLY_OBSERVED_INSTALLED_APP_NO_UPGRADE_BY_THIS_TASK"},
            "official_source": prior["official_source"] if prior else {"state": "UNKNOWN"},
            "manifest_permissions": prior["manifest_permissions"] if prior else {"state": "UNKNOWN_NOT_PARSED"},
            "effective_permissions": {"state": "UNKNOWN_NOT_YET_INTERPRETED", "role_status": "UNKNOWN_NOT_QUERIED"},
            "observed_failure_paths": prior["observed_failure_paths"] if prior else [],
            "runtime_acceptance": prior["runtime_acceptance"]["domains"] if prior else
                {k: {"state": "UNKNOWN_NOT_QUALIFIED", "evidence_refs": []} for k in
                 ("startup", "session", "core", "network_or_offline_continuity", "storage", "permissions", "long_running", "app_restart", "runtime_restart", "fault_recovery", "integrity", "hardware_if_required")},
            "latest_usable_version_qualified": False, "production_ready": False, "cleanup_eligible": False,
        }
        if package in effective:
            value, path = effective[package]
            assert value["uid"] in current_pm[package]["uids"] and value["version_code"] == current_pm[package]["version_code"]
            row["effective_permissions"] = {"state": "LITERAL_SERVICE_SNAPSHOT_INTERPRETED", "source": path,
                "details": value, "same_app_version_and_UID": True, "new_live_read_by_this_generator": False,
                "role_status": "UNKNOWN_NOT_QUERIED", "functional_permission_behavior_qualified": False}
        if package == "com.lianjia.beike":
            row["observed_failure_paths"].append({"state": "INDEPENDENT_SINGLE_CLICK_FAILED_UNKNOWN_PRESERVED",
                "source": beike_diag_path, "job": beike_diag["historical_job"],
                "helper_rejection": "INSPECTED_TREE_OR_WINDOW_CHANGED", "helper_action_attempted": False,
                "whole_case_outcome_unknown": True, "postcondition_completed": False})
        if package in ("local.pocket4.fixture", "org.chromium.webview_shell", "org.droidloom.qa.editorcontract"):
            row["observed_failure_paths"].append({"state": "INDEPENDENT_B13_CORRECTION_PASSED_ORIGINAL_FAILURE_PRESERVED",
                "source": coverage_path, "job": "1a1b2ba9875-fc05-7f80", "business_success_inferred": False})
        if package == "com.example.ndk_tests":
            row["PM_service_metadata"] = discovery["new_package_service_metadata"]
        rows.append(row)
    assert len(rows) == 46 and sum(r["original_eight"] for r in rows) == 8
    installed = [r for r in rows if r["upgrade"]["state"] == "INSTALLED_AND_CURRENT_BYTES_REOBSERVED_BUSINESS_QA_PENDING"]
    assert len(installed) == 11
    output = {"schema": "pocket4-current-launcher-inventory-v2", "state": "IN_PROGRESS_NOT_PRODUCTION_ACCEPTANCE",
        "target": "Pocket4 DroidLoom Android 17 / SDK 37 / user 0", "current_scope_job": joint["job_id"],
        "reDroid": "RETIRED_NO_CURRENT_TEST_TARGET_NOT_COUNTED_AS_PASS",
        "summary": {"Launcher_apps": 46, "non_APEX_APK_packages": 206, "normal_APK_audit_apps": 45,
            "normal_APK_audit_APKs": 85, "new_identity_only_apps": 1, "completed_upgrades": 11,
            "effective_permission_snapshots_interpreted": 3, "full_production_ready_apps": 0,
            "cleanup_eligible_apps": 0, "old_products_deleted_bytes": 0},
        "boundaries": {"new_ADB_dependency": False, "Bili_Accept_only": "p4-bili-m30-cell-20261010 / UID 1972",
            "Main_Bili_Accept_authorized": False, "Meituan_proactive_location_grant": False,
            "signature_or_integrity_bypass": False, "private_UI_or_permission_raw_included": False},
        "framework_memory_observation": memory,
        "international_delivery_research": {"source": international_delivery_path, "details": international_delivery},
        "Marriott_actual_public_delivery": {"source": marriott_delivery_path, "details": marriott_delivery},
        "apps": rows,
        "limitations": ["This is a join of exact observations, not a fresh functional test.",
            "Version names are installed APK manifest observations; they do not qualify the latest usable vendor release.",
            "Original failed batches and cases remain failed; independent corrective evidence is linked separately.",
            "Manifest declarations, PM literal grants and AppOps are distinct; roles and actual permission behavior remain unqualified.",
            "Absent runtime evidence is UNKNOWN; no launch, login, business, soak, restart or recovery success is invented."]}
    index = save("INVENTORY.json", output)
    save("INPUTS.json", {"files": list(INPUTS.values()), "output": index, "target_calls": 0})
    text = ["# 当前全部 Launcher App 清单与修复状态", "",
        "工作尚未完成。新实测为 **46 个 Launcher App、206 个非 APEX APK 包**；原定八个是其中子集。已完成 11 次同签名升级，原 45 App / 85 APK 的正常验签与 manifest 审计已独立联合通过。新增 NDK 测试包仅已核定实际身份，验签待完成。**生产验收通过 0，已删除旧产物 0 字节。**", "",
        "这份清单的版本列来自已装 APK 的 manifest，新增包另标 PM 观测；不能将其读成所有 App 都已是最新可用版。完整包名、组件、UID、versionCode、签名和 APK hash、声明权限、有效权限来源、真实失败路径及 12 个回归领域状态均在同目录 INVENTORY.json。", "",
        "## 全量清单", "", "| App（历史标签） | 包名 | 已装 versionName / code | 升级与审计 | 有效权限 |", "|---|---|---|---|---|"]
    for row in rows:
        pkg = row["package"]
        label = row["label_reference"] or "NDK 测试入口（标签尚未读取）"
        version = row["version_name"] if row["version_name"] is not None else "未声明" if pkg == "local.pocket4.fixture" else "UNKNOWN"
        status = "已升级；正常验签通过" if row in installed else "已装包正常验签通过" if pkg in audits else "新身份已绑定；验签待完成"
        if pkg == "com.zhubajie.client":
            status += "；9.5.20 候选已验签、未安装"
        elif pkg == "com.sankuai.meituan.takeoutnew":
            status += "；升级候选签名冲突"
        permission = "实际快照已解释；功能行为待验" if pkg in effective else "UNKNOWN（尚未完成有效权限解释）"
        text.append(f"| {label} | `{pkg}` | {version} / {row['PM']['version_code']} | {status} | {permission} |")
    text += ["", "## 当前实际阻塞", "",
        "贝壳已启动并取得首页节点，搜索动作两次被原 helper 的树/窗口一致性检查拒绝。新单击的 helper 明确未调用 performAction；整个 case 的 FAILED/UNKNOWN 保留，没有重放，也没有把首页截图当作搜索成功。", "",
        "美团新候选与已装包签名不同；没有强制覆盖、重新签名或卸载数据，位置权限也没有主动开启。12306 仍缺可安装的完整官方新包。猪八戒 9.5.20/code 370 已正常验签，与已装 9.5.11 同厂商签名，安装等待新的完整保护范围。14 个国际 App 尚未取得合格的完整新包；万豪普通公开入口实际 HTTP 403，原失败保留。", "",
        f"Framework 最新 RAM 观察为 {memory['observed_utc']}，MemAvailable {memory['values_bytes']['MemAvailable']:,} B，原 15 GiB 门槛差 {-memory['difference_from_original_minimum_bytes']:,} B；尚未重启构建。已有 builder 的资格验证不等于 framework 已编译或部署。", "",
        "## 回归与清理", "",
        "逐 App 的启动、登录或访客、核心操作、网络、存储、权限行为、长时间运行、App 重启、运行时重启和故障恢复尚未完整通过。已知结果保留原任务和文件 hash；未做的检查保留 UNKNOWN。旧 reDroid 已退役，当前内置 Android 的结果不转移为 reDroid 通过。", "",
        "完成对应生产验收后再删除旧 Android/framework、旧 APK、实验残留和中间产物。已识别 11 次升级留存的 12 个旧 APK，历史逻辑字节合计 2,136,945,962 B，但尚未测得当前可释放空间。旧 builder/tool 目录仍有现行依赖；最终源码、配置、正常签名 APK 集和复现清单必须先脱离拟删除目录。", "",
        "继续使用既有 sidecar、容器内 UI Automator、中文输入和节点定位。Bili Accept 只沿历史独立 cell 授权；美团位置权限不主动开启；完整性和签名检查保持。", "",
        "## 证据入口", ""]
    for name in INPUTS:
        text.append(f"- `{name}` — SHA-256 `{INPUTS[name]['sha256']}`")
    (HERE / "README.md").write_text("\n".join(text) + "\n")
    print(json.dumps({"summary": output["summary"], "inputs": len(INPUTS), "inventory": index}, sort_keys=True))


if __name__ == "__main__":
    main()
