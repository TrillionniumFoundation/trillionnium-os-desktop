# 全部 Launcher App 的离线回归验收入口

本目录把已经审阅的 **45 包、136 项核心用例、12 类网络/本地/服务 profile** 接入可执行的离线判定。交付的 evidence 是未执行模板：**所有应用 UNKNOWN，0 production ready，0 cleanup**。本目录没有执行设备 QA、安装、UI、权限、重启或清理操作。

## 固定原八项，补全其余应用

`evaluate_all.py` 核对原 `evaluate_readiness.py`、`regression_manifest.json`、`app_test_catalog.json` 的完整字节、长度和 SHA256 后才使用其内容。三个原文件不修改。

原 evaluator 已按 fresh resolver 迭代全集；缺口是 policy 只有八包具体业务流程，而且网络检查一律要求 App 自有 DNS/TLS。新增入口保留八包完整的原 `Audit.app` gate，再加每包 catalog case、网络适用性、硬件、输入、实际权限、数据身份和新 epoch 重测。其余商业包沿用相同商业 gate，系统/上游/本地 QA 走真实来源分支。

原八项的核心流程、会话模式、受控对端要求、官方域名和原安全/执行策略不可通过传入 policy 减弱。Bili Main `Accept` 必须未执行，不能转用独立历史 cell `p4-bili-m30-cell-20261010` 的许可；美团外卖不得主动授予 FINE/COARSE location；所有有效完整性和安全约束仍须保留。

## 本地复现

从 `pocket4_eight_apps` 项目根目录运行：

```bash
python3 -B readiness_all_launcher/evaluate_all.py --policy-template
python3 -B readiness_all_launcher/evaluate_all.py --template
python3 -B readiness_all_launcher/evaluate_all.py readiness_all_launcher/evidence.UNKNOWN.json
```

最后一条预期退出 **1**。退出 0 表示提供的声明满足当前离线契约，1 表示缺证据/不通过，2 表示无效输入或固定源不可读。程序不执行 Android 操作；`actions_executed=[]`；始终 `cleanup_eligible=false / cleanup_authorized=false`。后续清理还须原独立保留/精确路径 gate 和实际授权。

实际收据另存新文件，不覆盖 UNKNOWN 模板：

```bash
python3 -B readiness_all_launcher/evaluate_all.py ACTUAL_EVIDENCE.json --policy REVIEWED_POLICY.json
```

实际输入须明确 `template_only=false`，提供真实当前 runtime/helper/app 绑定和完整原件索引。工具不会生成这些事实。policy 中的 runtime hash、helpers 和新 artifact pins 默认 UNKNOWN；只有真实新资格及独立审阅之后才能填写。

本地边界测试：

```bash
cd readiness_all_launcher
python3 -B -m unittest -v test_evaluate_all
```

测试的接受对照只是在内存中构造局部 profile/lifecycle 声明，不产生设备 evidence，不代表 Android 行为通过。Revision 2 是 executor 失联后根据已见源码恢复的候选，重新运行测试；不继承此前未落盘文件的结果。

## Fresh resolver 集合是必需输入

旧 catalog 的 45 包不是当前 resolver 证明。实际完整 MAIN/LAUNCHER 查询必须绑定当前已审 runtime/helper，Android user 0，真实查询起止时间、非缓存查询证据、resolver generation、所有 package/components/system 分类和规范集合 hash，并正常结束全部查询进程。

`actual resolver packages == reviewed catalog packages == evidence.apps keys` 才允许全量通过。新增或缺失包都列入 `catalog_delta` 并阻断；新增包同时保留在结果 apps 中，即使别处 JSON 结构无效也不默默遗漏。不能靠卸载/隐藏 launcher 或缩小查询范围完成任务。正当集合变化需显式新 catalog/source revision 和审阅，本入口不自动扩权接纳。

## 版本、来源与独立 scope

runtime epoch/config/framework/helper 身份和可升级 App 安装身份分开。每包绑定当前包名、user、UID、版本、所有 base/split hash 与 signer 的 digest。合法升级后建立新 App scope；旧业务 PASS 不迁移。真实 runtime 重启后须全量新资格和每包当前 epoch 的核心/持久化重测。

| 类型 | 来源证明 | 必须同时成立 |
|---|---|---|
| 商业 App、上游发行的 microG/Fcitx | 正式来源、目标适用最新版、独立发行方 signer/轮换链 | 完整 APK/split、实际 apksigner 回执、安装字节一致、versionCode/完整 APK 集 policy pin、实际业务验证 |
| Framework 的 AOSP 组件/demo/WebView shell | 最终 qualified framework 的 source-lock/build manifest/包构建映射、授权平台 signer | 实际完整 APK 验签、当前字节和 framework source/artifact set 对应、真实 provider/renderer 能力 |
| 本地 owner QA | 最终源码/协议、build manifest、明确 owner signer、当前 helper 身份 | 真实构建成功、当前安装/UID、当前 epoch nonce 与拒绝路径，不能按包名猜协议 |

仅网页版本、未完成下载、语义版本更大或“密码学签名合法”不足以通过。额外的 `installed_artifact_pin` 固定 versionCode 和完整 APK 集，避免地区分发包被版本名误认。已装字节若已是经过完整验证的目标最新版，不要求重复安装来计数。

本地 QA 的真实 versionCode 可以是 0，系统组件可以共享 UID，源码可能未声明 versionName。仅完整 manifest 证明 `absent_in_verified_manifest` 才接受版本名缺省；UNKNOWN 不等于缺省。原八包版本身份规则不变。

## 每包验收

- **启动与会话**：响应首屏、真实进程/UI、无 crash/ANR；合法登录、实际可用访客或有本地组件契约证明的无需服务账号。必需会员、通信对端等不能因未提供而取消。
- **核心操作**：原八项已有流程全部保留；精确覆盖全部 136 个计划 case 和每项步骤、profile。真实结果、原 action、UI/接口读回缺一不可。硬件、provider、通知、文件、中文输入与双方通信回执按具体用例采集。
- **网络与服务**：使用下表 profile。实际启用的在线分支必须列入经过独立证明的配置清单，并有真实 actor/传输/返回/恢复；未读取配置不能填空表豁免。
- **存储与权限**：合成夹具的正常 API/provider 写入读回和重启持久化；UID、CE/DE device/inode/owner 或真实共享 provider 身份保留；完整 manifest、有效 grants/app-ops/roles 和拒绝/合法恢复证据。缺权限记录不是 deny。
- **长时与恢复**：保留本轮提出的至少 3600 秒连续实际采样、至少 3 次 App 真进程重启、至少 3 次适用依赖故障/恢复，以及一次真实 runtime 重启后的新资格和每包重测。这些是本轮提出的下限，不是历史已经通过的事实。
- **故障/安全**：未结算 action、账号/完整性/硬件缺口继续阻断。原失败和 UNKNOWN 保持原文；独立恢复/结算回执不改写原结果，不重放 UNKNOWN 制造成功。

| Network profile | 真实证明概要 | 故障循环 |
|---|---|---|
| vendor_https | App UID 请求、DNS/有效缓存、正常 TLS、业务返回 | 3 次网络失效/恢复 |
| vendor_rtc | 正常信令、受控双方文本回执、双向音频和挂断 | 3 次网络失效/恢复 |
| public_media | 真实播放请求、帧变化、音频、播放控制 | 3 次网络失效/恢复 |
| webview_https | 实际 provider/renderer、HTTPS/错误证书拒绝、DOM/JS/中文/存储 | 3 次网络失效/恢复 |
| offline_local | 实际本地组件/数据源、离线操作读回、本地故障恢复 | 3 次离线/在线变化期间本地连续 |
| system_settings | UI 与真实系统服务一致，断网/恢复后刷新 | 3 次本地连续/服务恢复 |
| local_search_with_delegation | 当前 provider、查询结果、真正执行的接收组件及返回 | 3 次委托服务故障/恢复 |
| cellular_telephony | 合法实际 SIM/电话账号、Telephony 服务、受控对端 | 3 次电话服务故障/恢复 |
| thread_ipv6_lan | 实际 radio/driver、受控 dataset/router、IPv6 收发 | 3 次 Thread 服务故障/恢复 |
| microg_service | 实际服务/selfcheck、受控 API 调用、已启用远端服务 | 3 次配置服务故障/恢复 |
| local_qa_contract | 当前源码协议/helper/UID/epoch、nonce、拒绝路径 | 3 次本地连续/探针恢复 |
| local_ime | 真 IME 候选/提交/InputConnection、UTF-8、焦点与离线输入 | 3 次离线连续/输入恢复 |

离线、电话、Thread 等 profile 不接受伪造的 `app_level_dns_tls_response_verified` 字段。在线功能由实际服务/执行者另取证，不强迫称为该 App 自有 DNS/TLS。

## 证据形状

Record 沿用 `status=pass, scope=production`、完整 binding 和非空 evidence_refs。每个 reference 具有真实 URI、SHA256、带时区采集时间、kind、相同 binding。程序不下载、不打开 URI，也无法认证捏造的业务声明；独立审阅必须读取原件及真执行终态。

`catalog_checks.cases.<id>` 固定去掉 actual_result 后的 case contract digest、实际观察步骤 digest 序列和所有 required profiles。每个 profile 必须 verified、有真实 observation 和指定 kinds。通信额外要求明确授权、自有受控对端、双方 nonce/时间关联；媒体必须真实硬件和动作；IME 不得用直接写 EditText 冒充输入法候选/提交。

`catalog_checks.network.branch_inventory` 固定当前配置 hash 和全部实际启用分支；policy 的 online_branch_review 独立 pin 配置/源码原证据。缺能力、配置未读或失败不能写成空集合。

`catalog_checks.inputs` 覆盖所有计划输入。通常为 supplied，具有真实引用、available/use_authorized；秘密不写入 JSON。仅从真实当前契约明确证明不需要的可选输入可记 not_required_by_verified_contract，且须独立 proof pin、原件、全部核心 case 仍执行、不是账号/硬件缺失或失败造成。它不跳过任何 case/profile。

此入口不自动删减带条件描述的核心用例。若某计划 case 确实不属于已经证明的当前产品契约，应保持阻断并提交显式 catalog revision 审阅；缺推送项目、电话硬件或账号不等于 N/A。

`data_identity.before/after` 包含 app_uid、android_user=0、storage_model、ce、de。存在目录须 state=present 与 device/inode/uid；实际证明不存在须 absent_verified 和单独 absence contract refs。shared/configuration provider 模式还须实际 providers 的 package/UID/component/identity digest。任意相等字典不能代替数据身份。

## 文件与实际状态

SOURCE_PINS.json 固定候选源码/测试/模板和三个原输入。LOCAL_TEST_RESULT.json 是本地控制结果；CURRENT_STATE.json 是 UNKNOWN 模板的离线拒绝摘要。实际设备成功安装的数量不在此模板中推导，也不等于生产可用。

真正验收还缺 fresh resolver、当前 helper 实编译/安装/资格，以及全部 APK/权限/业务/硬件/账号/长时/恢复收据。本目录没有 QA runner 或删除实现。
