# 全部 Launcher 的证据合并器

`build_matrix.py` 只读取共享项目已有证据，输出全部实际 Launcher App 的 JSON 与 Markdown。它不执行设备命令、不调用 Main、不申请原 audit ledger 的 claim，也不是生产资格或后续 mutation 的授权门禁。

## 已接入证据

- 原始 user 0 PM / MAIN+LAUNCHER 结果与 durable terminal、完整 owned child 输出；45 个组件必须与计划的 45 包完全对应，增加或减少一包都拒绝生成，不能静默过滤。
- 原 b01–04 通过冻结原 gate 验证；原 b05 失败与独立纠正审计同时保留；b06 之后通过原 linked gate 的 `owned_gate`、`complete_apk_gate` 逐项验证。未调用 `claim`。当前 b13 的完整失败终态和嵌入的 APK 结果仅作为失败批个体观察，绝不计入联合通过。
- 11 次真实安装的完整原始 stdout、durable terminal、唯一正常 native install、当前 scope 同 UID/code/证书/APK 字节及数据保留证明。京东的原 base + split 必须两件全部保留；jd-01 原失败不计安装。
- 每个当前 APK 的签名方案、证书摘要、版本名、min/target SDK、ABI、hash 与 manifest 权限声明。版本解析失败保持 null/UNKNOWN，历史版本名分列，绝不由 PM code 推导。
- microG / Fcitx 当前字节与之前官方 release 资产摘要相等；原官网 release 原文若本地缺失，会明确标明不可用，不伪装本次重新查询。美团候选与当前 signer 不同，升级保持 blocked。
- 贝壳已发布的 PM/AppOps 字面派生摘要；不读取私有业务原文。其余 44 包有效授权状态为 UNKNOWN。本轮新权限全量采集尚未纳入此 revision。
- 贝壳已发生的窄启动、只读 inspect 与 partial failed case。保留原 FAILED / UNKNOWN；不把后续只读首页观察认作搜索业务成功或新动作授权。

当前预期的固定实际统计是 **45 App / 85 APK 已尝试，42 App / 82 APK 通过联合审计，末批 3 App 未资格化；11 次升级，2 个官方资产摘要同字节，1 个签名冲突，0 生产就绪，0 清理**。这组结果会从原件重算，代码不把通过数当补齐目标。

## 运行

在项目根目录：

```sh
python3 -B audit_matrix_r1/check_boundaries.py
python3 -B audit_matrix_r1/build_matrix.py --write-snapshot
```

不带 `--write-snapshot` 时只验证并输出摘要。实际输出为 `snapshots/<输入清单 SHA256 前 20 位>/INPUTS.json`、`EVIDENCE_MATRIX.json` 和 `EVIDENCE_MATRIX.md`。每份输入在输出前重新读取并散列。新目录内 O_EXCL 写入；已有同一快照只能逐字节一致，不能覆盖不同内容。旧证据完全不修改。

完整 JSON 有意保留 base/split、literal 权限与每包验收合同，可能较大。Markdown 是人读表格；JSON 是可追溯明细。两者都不含私有 UI 树、窗口原文、账号、密码或业务数据。输入清单可能含已公开使用的 `app-scope.private.json` 文件名；该文件内容仅是 APK/UID/数据目录 inode 元数据，并不是 UI 私有 bundle。

## 解释限制

“当前”指这份实际记录的观测时点，不是生成器重新访问设备。成功 APK 验签不证明 vendor 来源、服务端 integrity 判定、账号可用、中文输入、核心业务、网络、存储、权限恢复或硬件能力。每包这些域仍为 UNKNOWN，只有窄的真实子观察独立记录。

60 分钟长时、3 次应用重启、3 次断网恢复是本轮提出的验收门槛，不是历史通过事实。不同离线/系统/硬件 profile 依各自合同取证；不以没有账号或硬件为 N/A。reDroid 没有当前测试目标，不能转移 Pocket4 Main 的任何结果。

本 revision 冻结 b13 原失败。后续针对无版本属性 fixture 的合法解析修复，需要新的显式证据和独立版本的合并器才能加入；不能在这里修改原失败或自动重分类。

## 本地控制

六组窄控制使用真实恢复的证据：新增/缺失 resolver 包拒绝、fixture PM code 0 不猜版本名、声明不推导 grant、JD 旧 split 不得遗漏、失败/缺完整终态不得通过，以及完整 45 包原件重新验证。所有测试只在本地主进程读取文件，末尾核对完整 FD 身份集不变。
