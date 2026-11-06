# Task 878 partial-case proof：下一阶段设计

状态：**仅设计；没有新 runtime worker、commit worker 或 process request；没有设备调用。**

固定对象仍是现有 flow
`/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe`，
未知例 `close-and-observe-search-01` 与后来独立观察
`inspect-after-search-rejection-01`。不创建第二个活跃业务 flow，不重播旧点击。

## 1. 已完成的真实前提

Host verifier 实际 job `1a1b2b679c3-fc05-7f6e` 已 durable / complete / exit 0：

- 完整 stdout：3,405 B，SHA256 `0033cfad5c04b9ed1b5ff8691c59a983ae790ed35a91282fc916a0c197240c4e`。
- 实际 terminal：731 B，SHA256 `4c755da48c16bdca5c577ab528ca21e43f60cd776f378a5fbba09e1fd866a351`。
- 已写历史 proof：52,310 B，SHA256 `2fc36b4de281ae511aff58d9fae7dc849b478fe07e1ccd5b3b7bc06a247507c3`，
  `/home/alex/work/pocket4-beike-partial-case-proof-20261106-r1/host-historical-proof.json`。
- 新 observer 私有原字节归档：810,742 B，SHA256 `1798e4de4e9b8799ab847f6b51cb98cf7b9ea224f1b44e2deebb5478c1f0b85c`。
  这份归档只留宿主私有路径，不能入 Git。
- 原例 29 个 command / 38 个 transport，后来观察 9 / 12，均按完整原件核验。
  原例仍 `case_ok=false`、`case_outcome_unknown=true`；host proof 没有当前 Main 权限或 reconciliation。

历史 proof 真实证明：第一步已执行，且独立后置观察成立；第二步 helper 在 dispatch 前因
`INSPECTED_TREE_OR_WINDOW_CHANGED` 拒绝，完整失败 wire、恢复状态和独立 after-state 相符；
原最终三 nonce 从未执行；后来另一次完整只读观察确实看到指定首页搜索节点。
它没有证明搜索页、中文查询或业务成功。

## 2. 冻结消费者实际接受什么

实际重建源码是
`successor_qa/reconstructed/source-generation-r2/recorder/recorder.py`，
39,563 B / `0e50c67b1d5d251766fb58a69d9e62e119f0663ff2c4115ae326874cf95d6c09`。

`Flow.begin(args, mutation=True)` 对每个旧 mutation 检查原 result，要求
`outcome_unknown is False` 或 `self.reconciled(old_step)`。cleanup 有原来的明确例外，其他操作没有。

`Flow.reconciled` 接受条件闭集如下：

| 字段 / 事实 | 冻结消费者的实际要求 |
|---|---|
| `schema` | `pocket4-flow-explicit-reconciliation-v1` |
| `unknown_step` | 当前被检查的旧 step 名字 |
| `epoch_sha256` | 原 flow.scope 的同一 Main epoch |
| `scope_sha256` | 当前原 `scope.json` 全字节 SHA256 |
| `original_action_outcome` | `unknown_retained` |
| `allows_new_decisions_only` | true |
| `evidence_sha256` | 每个 path 为 flow 内相对路径、没有 `..`；原 `read_regular` 全字节摘要相等 |
| 文件身份 | 原 `read_regular` 要求 regular、nofollow、nlink=1 |

消费者**不解释新 typed proof 的业务语义，也不查询 controller terminal**。
因此不能把若干通过字段手填进兼容 envelope 就称为正式对账。
新 producer 必须先完整证明自己的新协议，并明确记录其真实来源和终态。
冻结消费者、`Flow.begin`、`Flow.reconcile`、helper 和任何旧 result 都不修改。

旧 `Flow.reconcile` 只接受 `operation='ui'` 的旧 android-app click/set-text 与 dump/observe；
它不接受 owned-qa-case。这次的新 producer 会明确名为
`owned-qa-partial-case-reconciliation`，不会调用或假冒旧函数。

## 3. 采用两个新的执行阶段，禁止预封 commit

阶段 A 产生非授权 runtime candidate，并经正常 owned-child 退出及完整 controller 终态结算。
阶段 B 只能在 A 的真实原文全部取得并通过后封包；B 再执行原 foreground/task/helper 检查，
最后发布新的兼容记录。两个阶段分别用固定新 step / 新 source root / 新 key，不自动重试。

当前仅能准备 A 的源码。B 请求中需要 A 实际 job、stdout、terminal、candidate 字节、hash 和
parent-held pidfd 退出证据；这些现在不存在，必须保持未封包，不能放占位 PASS。

### 阶段 A：`owned-qa-partial-case-runtime-proof`

计划新 step：`partial-case-runtime-proof-01`。使用 `Flow.begin(..., mutation=False)`，
因为此阶段只读 Main 与写新宿主证明文件，不做 Android UI。这个分类不允许任何 `instrument`、
click、set_text、activation、launch、cleanup、install 或 permission 操作。

1. 用既有 bounded owner / libffi bootstrap 路径启动唯一子进程；父在放行前实际持有它的 pidfd。
   精确绑定已经实测的 Python / `_ctypes` / libffi 文件，不基线后移、不忽略未知 FD、不关闭库私有 FD。
2. 固定读取真实 host proof、host stdout / terminal、原两个私有归档、原 case / later observer 文件与
   全部 26 helper / recorder 源。完整字节与 full stat 前后相等。
   可以调用已冻结 `verify_partial_case_host.collect_and_verify` 的纯读取逻辑再核历史证据，
   但不能调用它的发布入口或改原 proof。重新计算的 canonical proof 必须等于真实 52,310 B proof。
3. 保持真实模块 `__file__`，从已部署原目录加载原 `qa_adapter` / `qa_contract` / recorder。
   通过原 `own_source` 和原 `qualified_build` 验证构建与签名来源。
   实际 build-result 为 UID 1000；沿原 `adapter.pinned/qualified_build` 读，不加假的 root owner 要求。
4. 创建原 `Flow`，使用新显式 operation / step；原 scope、baseline、qualification、guard 不改。
   按原顺序持有 flow.lock 和 global action lock，nonblocking 失败即停止，不等待争用。
5. `flow.bind()` 获得真实 R5 init / namespace / root / classpath / package / data authority。
   调用 `partial.binding_identity` 与冻结 `core.compare_held_bindings` 比较原 case、独立 observer、
   当前 held binding。只在原八个 nsfs 记录上按既有合同把 mtime 当观察时间；inode、dev、进程 start、
   APK / classpath / 普通文件全部字段仍严格相等，原记录不改。
6. 构造原 `adapter.Session(flow, recorder, qa, build, 10157)`。
   完整执行两轮：`installed()` → `task()` → `foreground()`。
   `installed` 每次两条 PM 命令与 held-root 全 APK hash；`task` 每次 exact leaf / 原 launch-scope；
   `foreground` 每次沿原 private backend 只读并保留 transport hash，不落无关窗口原文。
   合计 **6 个 recorded commands + 2 个 private foreground transports**，全部正常 join / lease release / post-guard。
7. 两轮实际结果完全相等。Helper UID 10157、37,008 B APK、签名来源、task 878 / 原 native receipt、
   user 0 / display 0 都必须与已经证明的原身份一致。
   调用原 `Session.foreground` 的 package predicate，保留其原错误字符串；绝不因旧 label 含 Bili 而改逻辑。
   完整 foreground scope（包括 activity/window token）还必须等于后来真实 observer 的前后 scope。
   这里只证明当前 scope 与那次观察相同，不声称当前树仍相同。
8. `flow.guard` / 源闭包 / 原档 / request / 当前 binding 再验后，`flow.close()` 退还全部 Main authority。
   所有子命令已 join；只保留明确知道的原 flow/global 锁及实证 libffi 资源直至该 owner 正常退出。
   完整 FD 集必须恰好符合预期，任何新增、替换或未关 FD 都拒绝。
9. 只在新 proof step 写 `runtime-candidate.json`、新 `result.json` 和必要的源 / 请求 / 原 host proof 副本。
   result 明示 `reconciliation_published=false`、`current_action_authority=false`、原 case FAILED/UNKNOWN 保留。
   此时不存在 `reconciliations/close-and-observe-search-01.json`。
10. 子进程正常 0 退出后，父用原 held pidfd 确认死亡，父 FD 全集恢复，才发布新的 joint artifact。
    root 仍须取得完整原 stdout / 空 stderr / 正常 durable exit 0；缺任何一层不能封 B。

### 阶段 B：`owned-qa-partial-case-commit`

计划新 step：`partial-case-commit-01`。仍是新的显式 producer，仍 `mutation=False`，Android UI 为 0。

封包前先严格核 A 的实际 source / request / job / stdout / terminal / candidate / parent-held pidfd 联合结果，
不得凭 A 的内层 candidate 文件或当前 root 口头状态封包。原 host proof 成功也不能替代 A。

B 使用相同原 Flow / R5 / `qualified_build` / `Session.installed/task/foreground` 再完成两轮同样的只读检查。
这是为了处理 A 结束后到 B 期间可能变化的真实前台、task、helper 或 epoch；不借 A 的旧 PID/FD 作当前身份。
若前台变成 IHG 或任何不符对象，照原 predicate 拒绝，无激活、resume 或换 flow。

只有当前检查、历史文件全部不变、所有命令正常收口、Main authority 关闭、最终 FD 集正确后，才写 typed proof。
typed proof 必须引用 A 的**已完成**正常 owned-child + durable terminal；不能预称 B 自身未来的正常退出。

新兼容 envelope 仅发布到原 flow 下唯一允许的
`reconciliations/close-and-observe-search-01.json`，且必须从不存在开始。
沿已审 `commit_envelope` 的 no-replace 协议：同目录 O_EXCL 私有 temporary → 完整写 / fsync →
`os.link` 到唯一最终名字 → unlink 自有 temporary → fsync 目录 → 全字节回读。
两个 hardlink 同时存在时 nlink=2，原消费者拒绝；任何已有最终名字或自有临时冲突都停止，不覆盖、不删除别人文件。

发布期间原 flow/global 锁保持。envelope 必须引用 flow 内原 case 全部文件、独立 observer 全部文件、
A 新 proof step / joint 来源与 B 新 typed proof 的精确相对路径和 hash。
外部私有 bundle 只作为被固定的输入，不伪造成 flow 内相对文件；不复制 UI 私有原文去公开目录。

**发布后的终态仍是必需门槛。** B 的正常 owned-child/pidfd 和 root 收到的 durable terminal 只能在实际退出后成立。
冻结消费者本身不检查 B controller，因此协调器必须保持 Main 新动作冻结直到 B 完整联合成功。
这不是声称 frozen Flow 会自动检查该终态。若 link 后发生异常，即使最终文件存在也按 publication UNKNOWN 保留，
不自动再发布、不删文件、不准运行下一动作；先依据同 job / exact envelope / 原 evidence 做独立只读对账。

## 4. Typed proof / envelope 字段的真实含义

运行阶段的新 proof schema：`pocket4-owned-qa-partial-case-runtime-candidate-v1`。
提交阶段的新 proof schema：`pocket4-owned-qa-partial-case-committed-proof-v1`。

以下字段必须为常量，不由 caller 任意传入：

| 字段 | 值 |
|---|---|
| target | `com.lianjia.beike` / UID 10143 / user 0 / display 0 |
| flow / task | 上述原 flow / 878，原 native scope 与全 64 位 native object id 原文保留 |
| helper | `org.droidloom.qa.successor.p8f89f253350ba2fa.r1` / UID 10157 |
| original case | `close-and-observe-search-01` / `case_ok=false` / `case_outcome_unknown=true` |
| later observation | `inspect-after-search-rejection-01`，真实完整 wire / nonce / 原字节 pins |
| producer | `owned-qa-partial-case-reconciliation`，`original_Flow_reconcile_called=false` |
| retained outcome | `original_action_outcome=unknown_retained`、`original_results_rewritten=false` |
| old replay / business / production | 全为 false |
| new Android instrumentation / UI / permission / install / lifecycle | 全为 0 |

完整证明分层存储：历史成功前缀、typed failed-helper pre-dispatch / restoration 证明、后来真实独立 postcondition、
当前 R5/task/helper/foreground 检查、A 的实际 owner/terminal、B 的当前检查与发布来源。
后续 mutation 仍由原 Flow.begin、原新 inspect、唯一 selector、完整 tree/window 双 hash、target refresh / final window 等门槛控制。

envelope 保持原 schema 供 frozen consumer 检查，同时明确扩展：
`new_owned_qa_producer.schema`、`proof_relative_path`、producer/core SHA、已完成 runtime candidate 的 job/terminal/hash。
不得写 `matched_native_node` 去冒充旧 backend 协议；新 helper 的匹配只在明确标注的 typed proof 中记录。
匹配内容是历史观察，不能叫“当前页面授权”。

## 5. 最小验证和停止条件

已有 268 + 81 原始文件的 host PASS 不再靠大套 synthetic 正例替代。下一版只新增必要边界控制：

1. A 或 host observer 不是完整 durable 0、pidfd 未确认正常退出、stdout/hash 不匹配时不能封 B。
2. 实际当前 foreground/helper/task/epoch 与既有合同不符时拒绝；不得改原 Session predicate。
3. 原 UNKNOWN 字节变化、namespace inode/dev/进程 start 变化、普通文件时间变化仍拒绝；仅既有 nsfs 观察时间例外可接受。
4. 自有临时目录内演示 no-replace 发布；已有目标和中途写失败均不能覆写；不创建真实 flow receipt 来测试。

如果当前前台、helper、task 或历史证据无法满足条件，保持旧 UNKNOWN。已证明合法的原 exact-owned-task cleanup
仍是故障恢复途径；它与这份 reconciliation 设计分开，不自动调用。

## 6. 明确不变

不修改原 helper / adapter / recorder / `Flow.reconciled` / baseline / guard / 本轮历史 core。
不更改当前全45审计或45权限采集范围；Beike编译scope只用于本 flow，不借给其他包。
不执行 Main Bili Accept，不主动授予美团位置，不接受完整性绕过。私有 UI / 归档不入 Git。
所有新远端执行仍由 root 完整二审和协调独占窗口后发起；本文不包含可直接启动的请求。
