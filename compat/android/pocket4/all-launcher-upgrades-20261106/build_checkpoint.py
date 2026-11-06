#!/usr/bin/env python3
"""Build a factual checkpoint from recorded Pocket4 observations, never run Android.

Nested JSON is parsed by Python so nanosecond stat integers remain exact.
Missing execution receipts stay UNKNOWN. This is not the readiness auditor.
"""
import datetime
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read(name):
    return json.loads((ROOT / name).read_text())


def pin(name):
    raw = (ROOT / name).read_bytes()
    return {"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def main():
    inventory = read("reference/current-all-launcher-metadata.json")
    catalog = read("app_test_catalog.json")
    assert len(inventory["apps"]) == len(catalog["apps"]) == 45
    assert {a["package"] for a in inventory["apps"]} == {a["package"] for a in catalog["apps"]}
    eight = {a["package"]: a for a in read("reference/current-original-eight-inventory.json")["apps"]}
    updates = {}
    for name in ("reference/beike-install-attempt3.json", "reference/ceair-install-attempt1.json",
                 "reference/airchina-install-attempt1.json"):
        if not (ROOT / name).exists():
            continue
        wrapper = read(name)
        result = wrapper["result"]
        if result.get("install_verified") is True:
            assert result["outcome_unknown"] is False and result["errors"] == []
            assert result["data_directory_identity_retained"] is True
            updates[result["package"]] = {"evidence": pin(name), "job_id": wrapper["job_id"], "actual": result}
    candidates = {}
    for name in ("reference/beike-official-verification.json", "reference/bilibili-official-verification.json",
                 "reference/ceair-official-verification.json"):
        raw = read(name)
        value = raw.get("actual_verifier_result", raw.get("result", raw))
        if isinstance(value, dict) and "package" in value:
            candidates[value["package"]] = {"evidence": pin(name), "actual": value}
    for value in read("reference/launcher-candidate-verifications-r2.json")["results"]:
        candidates[value["package"]] = {"evidence": pin("reference/launcher-candidate-verifications-r2.json"), "actual": value}
    apps = []
    for observed in sorted(inventory["apps"], key=lambda a: a["package"]):
        package = observed["package"]
        names = observed["launcher_entries"]
        historical = observed["historical_version_name_references"]
        row = {"package": package, "launcher_name": names[0]["name"],
               "launcher_components": [v["component"] for v in names],
               "uid": observed["uid"], "installed_version_code": observed["version_code"],
               "installed_version_name": None, "version_name_reference": next((h["version_name"] for h in historical if h.get("version_name")), None),
               "version_name_authority": "HISTORICAL_REFERENCE_ONLY_CURRENT_MANIFEST_NOT_READ",
               "code_path": observed["code_path"],
               "package_manager_certificates": observed["package_manager_signing"]["certificate_sha256"],
               "permission_observation": "SAVED_STATE_COLLECTED_EFFECTIVE_RUNTIME_STATE_UNKNOWN",
               "upgrade_state": "LATEST_USABLE_UNPROVEN", "business_qa": "UNKNOWN_NOT_RUN_IN_THIS_CHECKPOINT",
               "production_ready": False, "cleanup_eligible": False}
        if package in eight:
            row["original_eight_full_byte_observation"] = True
        if package in candidates:
            c = candidates[package]
            value = c["actual"]
            row["candidate"] = {"manifest": value.get("manifest"),
                "status": value.get("status"), "signature_verified": value.get("signature_verified", False),
                "signer_matches_historical_installed_reference": value.get("signer_matches_historical_installed_reference"),
                "matches_latest_observed_store_version": value.get("matches_latest_observed_store_version"),
                "evidence": c["evidence"]}
            row["upgrade_state"] = "CANDIDATE_OBSERVED_NOT_INSTALLED"
            if value.get("status") == "VERIFICATION_FAILED":
                row["upgrade_state"] = "CANDIDATE_REJECTED"
                row["candidate"]["failure"] = value.get("error")
        if package == "com.sankuai.meituan.takeoutnew":
            row["upgrade_state"] = "BLOCKED_OFFICIAL_SIGNER_DIFFERS_FROM_CURRENT_RESIGNED_APP"
            row["location_grants_authorized"] = False
        if package == "tv.danmaku.bili":
            row["upgrade_state"] = "VERIFIED_CANDIDATE_PENDING_PRIOR_LAUNCH_UNKNOWN_SETTLEMENT"
            row["guest_accept_in_current_cell_authorized"] = False
        if package in updates:
            u = updates[package]
            result = u["actual"]
            after = result["after"]
            row.update(installed_version_code=after["target"]["version_code"],
                       installed_version_name=result["official_verifier"]["manifest"]["version_name"] if "manifest" in result["official_verifier"] else candidates[package]["actual"]["manifest"]["version_name"],
                       version_name_authority="EXACT_VERIFIED_APK_HASH_READ_BACK_AFTER_NATIVE_INSTALL",
                       code_path=after["target"]["code_path"], upgrade_state="INSTALLED_AND_BYTE_VERIFIED_BUSINESS_QA_PENDING",
                       installed_apk=after["base_apk"], data_directory_identity_retained=True,
                       install_receipt=u["evidence"], install_job_id=u["job_id"], install_finished_utc=result["ended_utc"])
        apps.append(row)
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    status = {"schema": "pocket4-all-launcher-progress-checkpoint-v1", "generated_utc": timestamp,
        "scope": "ALL_45_OBSERVED_NATIVE_LAUNCHER_PACKAGES",
        "catalog_current_android_resolver_proven": inventory["catalog"]["current_android_launcher_resolution_proven"],
        "observed_runtime": "Pocket4 DroidLoom Android 17, SDK 37, Android user 0",
        "runtime_epoch_sha256": inventory["epoch_sha256"],
        "redroid": "RETIRED_NO_CURRENT_TARGET_NO_NEW_TEST_COVERAGE",
        "inventory_source": pin("reference/current-all-launcher-metadata.json"),
        "test_catalog_source": pin("app_test_catalog.json"),
        "installed_and_verified_updates": len(updates), "whole_app_production_passes": 0,
        "test_cases_planned": sum(len(a["core_cases"]) for a in catalog["apps"]) if all("core_cases" in a for a in catalog["apps"]) else catalog["actual_summary"],
        "framework": {"provider_builder_compiled_and_qualified": True,
            "normal04_soong_launched": False, "normal04_stop": "FRESH_RAM_BELOW_UNCHANGED_15_GIB_ADMISSION",
            "mem_available_bytes": 15927521280, "required_bytes": 16106127360,
            "production_ready": False},
        "native_recovery": "READONLY_PREFLIGHT_PASSED_EXECUTION_PENDING",
        "qa_successor": "SOURCE_CANDIDATE_ONLY_NOT_BUILT_INSTALLED_OR_ADMITTED",
        "cleanup": {"eligible": False, "performed": False, "bytes_reclaimed": 0,
            "condition": "All current launcher Apps and final framework genuinely qualified; unresolved outcomes settled; final working source/configuration/reproduction manifest retained"},
        "apps": apps}
    (ROOT / "current_status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n")
    rows = []
    for a in apps:
        name = a["installed_version_name"] or ("参考 " + str(a["version_name_reference"]) if a["version_name_reference"] else "未读取 manifest")
        candidate = a.get("candidate", {}).get("manifest") or {}
        rows.append(f'| {a["launcher_name"].replace("|", "/")} | `{a["package"]}` | {name} / {a["installed_version_code"]} | {candidate.get("version_name", "待核实")} | {a["upgrade_state"]} |')
    body = f'''# Pocket4 全 Launcher 升级检查点

记录时间：{timestamp}。这是实际进度检查点，任务尚未完成。

## 当前结论

已核对原生 Launcher 目录中的全部 **45 个包**，现有 **{len(updates)} 个 App 完成实际升级并读回验证**。完整业务与长时、重启、故障恢复验收仍为 **0/45**；没有把下载、编译、安装或短时启动等同于 production ready。

当前目标是 Pocket4 DroidLoom Android 17 / SDK 37 / user 0。历史 reDroid 已退役，没有当前容器目标，本轮没有重建它或迁移旧测试结论。目录前后两次原生读取一致，但其缓存是否等同当前 Android MAIN/LAUNCHER resolver 尚未证明；须在重新绑定的 Android QA 中再枚举。

## 已有实际证据

- `reference/current-all-launcher-metadata.json`：45 包 PM 版本码、UID、代码路径、证书摘要和保存的权限记录；保存状态不冒充有效运行时授权。
- `reference/current-original-eight-inventory.json`：历史八包的完整当前 APK 字节核对；之后的成功升级以各安装回执覆盖旧版本。
- 独立安装 worker 通过既有 native sidecar 路径提交已验签、相同签名的精确 APK，读回新安装字节，并核对 UID、数据目录、其他七包身份和美团位置记录连续性。没有引入 ADB。
- `app_test_catalog.json`：全部 45 包、136 个具体核心 case；全部为 `UNKNOWN_NOT_RUN`。本地、电话/SMS、Thread、IME 与商业联网 App 各有实际适用路径，没有用 N/A 伪造网络通过。
- `framework_provider_repair/`：真实 provider 源修复，Rust builder 实编译及 16 个 focused tests 成功。normal04 的完整 Android/Soong 构建在实际内存准入前停止：15,927,521,280 B 小于固定 16,106,127,360 B 门限，未降低门限，也未把局部编译当作 framework 部署完成。
- `recovery/`：现有 cell 的正常原生 restart 候选和真实只读 preflight。该检查点时尚未执行 restart，新 QA 也尚未实构建/安装。

## 不能略过的边界与失败

Bilibili 的历史 guest Accept 只适用于 `p4-bili-m30-cell-20261010`，当前 Main 不获得 Accept 授权。此前 task 873 的 native ownership 冲突与不确定 launch 回执原样保留；不按 task ID 删除或夺取所有权。美团外卖不得主动开启位置权限；它当前重签名 APK 与官方签名不一致，不能通过重签名、卸载丢数据或绕完整性检查强行升级。

官方下载入口也存在旧包/错包：京东所取 APK 包名不匹配；携程 metadata 是 8.97.2、公开下载入口却返回名为 8.94.6 的包；抖音真实官方下载在 deadline 前未完成。这些都不算更新成功。国际商店登录、商业完整性、合法测试账号/受控通信对端或硬件缺口，需要真实条件才能验收。

## 逐包状态

“参考”版本名来自历史 manifest，不冒充本轮刚读取的当前 manifest。版本码来自本轮 PM 保存记录；成功安装行的版本与字节已实际读回。全部行的完整业务回归仍待执行。

| Launcher 名称 | 包名 | 已安装版本名 / code | 已取候选版本 | 状态 |
|---|---|---|---|---|
''' + "\n".join(rows) + '''

## 复现和继续执行

`build_checkpoint.py` 只汇总已经存在的 JSON 回执，不运行 Android。`evaluate_readiness.py` 是离线证据审计器，当前 `regression_manifest.json` 的具体逐包策略仍只覆盖历史八包；新 45 包适用性目录还需显式接入后才可作为最终审计入口，不能把其模板当作已测结果。

所有升级、恢复和 QA worker 都按具体来源、版本、runtime 和单次操作绑定。成功回执是已经执行的记录；不能重新执行旧 flow 或改旧 PASS 的 PID、epoch、版本来伪造新授权。恢复前先结算所有已知相关 jobs，取得新的协调 drain，重新检查当前 source/CLI/运行时，再提交具体单次操作；细节见 `recovery/README.md`。

## 结束后的空间清理

用户已授权在最终可用版本验收之后删除所有旧 Android framework、旧 App、实验产物和中间构建。此检查点尚未达到条件，**没有执行旧版本清理，回收空间为 0**。最终保留可工作的源代码、精确 source-lock、当前配置、最终包/签名/来源清单、复现入口和轻量验收/故障结算回执。实际清理必须对待删路径逐一与正在运行、最后可用版本及未结算操作依赖核对，不用通配删除推测旧版本。
'''
    (ROOT / "CURRENT_STATUS.md").write_text(body)
    print(json.dumps({"apps": len(apps), "installed_updates": len(updates), "production_passes": 0,
                      "status": pin("current_status.json"), "report": pin("CURRENT_STATUS.md")}))


if __name__ == "__main__":
    main()
