# 45 个 Launcher App 的只读权限观察设计

本文件是实施设计，不是执行请求。没有生成 45 份 worker、传输封包、idempotency key 或 claim，没有新增远程过程。已经冻结并正在由 root 执行的 APK 审计源、原 ledger、Beike UI helper/Flow 均不修改。

## 依据与目标

以已经实际成功的 Beike 单包权限 pilot 为唯一运行实现基线：job `1a1b279845c-fc05-7e2e`，完整 worker 为 37,959 字节、SHA `42c94840e2e26ceeb2236bb01cff8787f1ae6440630ff481c73ab8007d61c01d`。它已真实完成当前 typed guard、47 包上下文、原 held namespace transport、原生 status/applications/status、三个只读 Android 命令、全部 FD/lease 和 owned child 生命周期收口。

目标名单取自实际 PackageManager MAIN+LAUNCHER resolver 与原生目录两轮一致的 45 包集合。原 r4 同时观察到的 user0 非 APEX APK 安装集合有 205 包；本设计只覆盖这 45 个 Launcher 包，不能称为 205 包全量权限审计。两个独立 helper/actions 包仍在 47 包身份保护范围内，不作为本轮业务权限目标。

每批保留实际 `44f9ce783000a672c270e98afdaeb74bd79654508bfacae6793316ff4252e52f` 的 47 包 scope 引用，以及 `d84df98d55352ef9ae66753ee15f3746d9d9a64c35fddf392a08f10ba4105cb3` 的 typed guard。执行时必须重新核对实际运行身份和整个 47 包范围；设计中存在的旧引用不能替代该检查。

## 闭合命令范围

只复用 pilot 已真实执行成功的命令形态，包名只能来自固定目标清单，参数按 argv 元组传递。

| 命令 | 已有实际依据 | 可记录的事实 | 不能据此声称 |
|---|---|---|---|
| `/system/bin/cmd package help` | pilot 返回 0；原文 40,229 字节、`a58bc737…` | 本次服务仍声明 `dump-package PACKAGE` 接口 | 其他未执行接口可用 |
| `/system/bin/cmd package dump-package PACKAGE` | Beike pilot 返回 0，完整输出 50,525 字节、`001c37aa…` | 对应包的服务报告；明确 user0 子块中的 runtime grant 与 flags；原样 requested/install 行 | 命令本身具有 user0 过滤；缺失行等于 denied；所有能力最终可用 |
| `/system/bin/cmd appops get --user 0 PACKAGE` | Beike pilot 返回 0，完整输出 1,720 字节、`f8390748…` | 该调用返回的 operation/mode 字面值及明确出现的 UID 前缀 | mode 等于权限 grant；default/foreground 等于无条件允许；未列项等于 deny |

不再运行 `appops help`：其历史实际返回 255 及 FAILED 保留，只将该完整帮助原文与实际成功 get 的原始回执作为语法依据。不会把历史 help 的 255 改为 0，也不改变 transport 对非零返回的停止语义。

当前没有已实际执行并确认语法与输出的 role 查询。**全部目标的 role 状态继续为 `UNKNOWN_NOT_QUERIED`**。package dump 中出现角色相关字符串或权限不构成 RoleManager 角色资格。若后续需要角色证据，必须先形成独立、固定、只读的真实接口证据；本设计不生成猜测命令，也不改变角色。

## 13 批、有界串行

沿用原 APK 审计的 13 个固定分区，每批 1–4 包；具体名单、当前引用 UID/versionCode 和证据 pin 见 `DESIGN.json`。前两批各一包，中间十批各四包，末批三包，共 45 包。

每批只包含一次 package help，以及每个目标的一次 dump-package 和一次 AppOps get；总计 `13 + 2 × 45 = 103` 条既有只读 Android 命令。包括 Beike 的新观察将记录新的采集时间，已有 pilot 不会被覆写或伪装成这次结果。全部批次是各自时间窗口的记录，不声称 45 包在同一瞬间完成原子快照。

只准备一个由 pilot 最小适配的固定目标集 collector；每批编译/封入具体目标 argv 顺序、scope、输入 pin、source/output root。这里的“适配”是新独立 collector 的范围，绝不向已编译的 Beike 两包 UI binding 添加其他包，也不扩张旧回调或 Bili 会话。

执行流程保持 pilot 的实际次序：

1. 创建独立 root 私有结果目录和单次 flow intent，获取原 action lock 与 flow lease。
2. 读取固定 guard，持有当前八角色和 init 的真实句柄，核全 47 包身份、UID、CE/DE 和 APK 字节；保持原 Bili UNKNOWN 检查与美团位置保存态快照。
3. 固定 CLI/daemon 身份，沿原 UID1000 caller 读取 native status、applications。将 native 的 package/component 集合与实际 45 resolver 证据逐项比较。新增、缺失或组件变化需明确记录并停止旧固定范围；数量相同不算身份相同。
4. 沿原 `HeldTarget`、七个 authority FD、固定 classpath/env 和 `BoundArun`，按闭合顺序查询本批权限服务。每条仍通过前后 guard，先记实际子进程结果，再持久保存原始 stdout/stderr，零长流使用已修复的安全 writer。
5. 再读 native status，核全 47 scope、同一 typed guard、Meituan 保存态和原 Bili UNKNOWN，不进行任何修正性写入。最后按原顺序关闭 target、释放锁、关闭 observation/lease FD，并等待 owned child 的原始 pidfd 退出。
6. 外层完整 stdout、原始 authoritative terminal、worker 和完整 FD/child 回执共同结算。解析服务正文是独立阶段，不能用“正文似乎合理”替代正常命令退出或资源收口。

保持 pilot 的每条命令 30 秒、每流 262,144 字节、worker 总预算 900 秒及已证 owned-child/外层预算。四包最多九条 Android 命令，没有提高原每条命令或输出上限；其余时间用于实际身份复核和收口。遇到输出界限、非零返回、truncation、timeout、guard/scope 差异或无法证明退出，即保留原结果并停止该执行链，不自动换 key、重跑或改变权限。

root 仍是唯一调度者。各批与任何 UI、安装、框架生命周期动作串行占用原 action lock。这里只提出批次，不占用执行窗口。

## 原始输出与解释分开结算

第一层只声明 `SERVICE_RAW_CAPTURE_COMPLETE`：闭合集合内命令全部正常退出、原始流完整保存、运行身份和完整资源收口通过。第二层才声明哪些字面权限字段已成功解释。不能将第一层成功写成“有效权限全部已确认”。

PackageManager 的解释边界：

- 按真实包头确认唯一目标，核服务中可辨认的 UID/version 与 scope；`dump-package` 不带 user 过滤，所以只选择这个目标包中的明确 `User 0` 子块。其他用户的行不进入公开结果。
- requested permission 只去除已经确认的展示缩进，名字原始空格原样保留。Beike 的七个前导空格 `VIBRATE` 名与正常名字是两个不同字符串。
- install 和 user0 runtime 条目分别保存。只有明确 `granted=true/false` 的实际行才形成该观察时刻的 PM 报告状态；flags 字面保留，不猜测是谁授予/拒绝，也不将 flags 推导成角色或业务可用性。
- 对未出现、重复、冲突、包/用户不明确、结构未认识的行，保留私有原文和解释问题，字段标 `UNKNOWN`；不沿用 Beike 的固定 63/26/15 行数，不将缺少 runtime 部分解释成“所有权限已授予”或“全部被拒绝”。
- shared UID、系统包和 UID 小于 10000 的目标均保留，不排除；记录真实 UID 上下文，不把一个 UID 的观察自动归因到所有同 UID 包。完整权限定义、隐含授权及特殊访问是否在本输出中体现，按实际字段分别处理。

AppOps 的解释边界：

- 每行保留 operation、mode 和原始行哈希。明确 `Uid mode:` 前缀按该行记录，未显式标出的行不猜测 UID/包层级，也不把首行前缀推广到后续整段。
- `allow/ignore/deny/default/foreground` 保持字面值；不合并成单一“有效允许”布尔值。缺失 operation、空返回或未知格式只有实际观察/未知含义，不自动成为 deny。
- 使用历史时间、attribution 或业务内容不进入公开派生结果；必要原文仍在私有证据中。`INTERNET granted` 不证明联网成功，媒体/文件权限记录也不证明真实文件访问成功。

最终每包至少保存：目标 package/UID/version、runtime/47scope pin、job 和命令流 pin、采集时间窗口、requested/install/user0 runtime 的可解释字段、AppOps 字面模式、每项未知原因、role UNKNOWN、以及零权限写入声明。之后才与已通过的完整 APK 声明权限结果做逐名字交叉引用；manifest 声明与当前服务授权并列记录，不能互相替代。

## 隐私与归档

PM/AppOps 完整正文可能包含附带的私人状态。延续 pilot：远端结果在独立 root 私有目录，读回后放在 repo 外的私有证据目录；Git 仅保存 source/request、durable 终态、服务流 byte/hash pin、资源收口元数据和必要权限派生结果。不得把含正文的 host-reader stdout/read 原件混入公开归档。

现有 Beike 公开派生结果已经确认 63 个 requested 名、26 条 install 记录、15 条 user0 runtime 记录（1 true、14 false）和 58 条 AppOps 字面模式。它明确保留 role UNKNOWN、非规范名字和语义限制。本设计只引用该公开文件，不读取或复制其私有正文。

本设计不会授予、撤销、重置任何权限或 AppOp，不启动 App，不点击弹窗，不输入文本，不安装，不重启，不读取业务数据文件。它补足真实服务状态证据；应用核心操作、拒绝权限后的恢复、长时间运行和 production readiness 仍须各自实际回归。
