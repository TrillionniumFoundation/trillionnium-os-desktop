# Beike task 878：阶段 A 的真实运行时候选

状态：**本地源码与固定请求已准备；没有提交设备，没有执行 Main，没有发布 reconciliation。阶段 B 仍未实现或封包。**

这份候选接续已真实成功的历史 verifier `1a1b2b679c3-fc05-7f6e`。
它保留 `close-and-observe-search-01` 原来的 FAILED / UNKNOWN，并只检查同一现有 flow、task 878、helper 10157、原 Main epoch 与原包 scope。
原 recorder、helper、`Flow.begin`、`Flow.reconciled`、`Flow.reconcile`、Session 和安全 guard 都没有修改。

## 固定对象与入口

新的宿主源码目录是：

`/home/alex/work/pocket4-beike-partial-case-runtime-20261106-r1`

现有 flow 仍是：

`/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe`

新增 step 仅为 `partial-case-runtime-proof-01`，显式 operation 为
`owned-qa-partial-case-runtime-proof`，调用原 `Flow.begin(..., mutation=False)`。
这表示只读 runtime 和写入新的宿主证明文件；它不提供 UI、instrumentation、launch、cleanup、activation、安装或权限操作。

唯一可审核的提交包是 `process-request.review-only.json`。它包含固定 stager 源和四个文件的原字节 payload，
由 root 统一协调提交。不得从本文复制片段另造请求、替换 key 或遇 UNKNOWN 后重放。

| 项目 | 已封闭参数 |
|---|---|
| 可执行程序 | `/usr/bin/sudo` |
| 参数前缀 | `-n /usr/bin/python3 -I -B -c` |
| idempotency key | `pocket4-beike-task878-partial-case-runtime-stage-a-r1-20261106` |
| 外层总限时 | 900 秒 |
| 唯一 owned child 限时 | 600 秒 |
| worker 自身总 deadline | 540 秒，原历史 verifier 另有 180 秒固定读取限时 |
| 资源包络 | CPU 100%，MemoryMax 1 GiB，nice 10 |
| 源码部署 | 新 root 私有 0700 目录，四文件 O_EXCL / nofollow / root 0400 / fsync / full stat 回读 |
| parent 入口 | `runtime_stage_a_once.py --execute-runtime-once --source-sha256 … --source-bytes … --request-sha256 … --request-bytes …` |

`PACKET_REVIEW.json` 和 `SOURCE_PINS.json` 给出全部精确长度与 SHA。
`stage-against-actual-host.diff` 是相对已实测 6,215 B host stager 的差异；文件写入、回读和 FD 门槛没有变。

## 接受链

1. parent 固定读取实际 host stdout 3,405 B 和 terminal 731 B。必须是上述 job 的完整 durable exit 0，
   两路日志完整、stderr 为零、无 timeout/cancel/retry；内层 host proof 文件本身不能替代这层终态。
2. 通过原 `probe.run_owned_child` 创建唯一子进程。父拿到它的真实 pidfd 后才发送原握手字节；
   child 使用已经实机验证的 Python / `_ctypes` / libffi bootstrap。唯一库资源被精确绑定，不能用“允许多一个 FD”代替。
3. 原 `collect_and_verify` 完整重核失败例、独立 observer、26 源闭包、原始命令和完整字节归档。
   重新生成的 proof 必须与真实 52,310 B / `2fc36b4d…` 完全相同，observer archive 必须与真实 810,742 B / `1798e4de…` 完全相同。
   不写回两个原文件，不重新生成旧 UNKNOWN，不在 stdout 输出私有 UI。
4. 原 `own_source` 和 `qualified_build` 读取实际构建凭据。构建文件真实 owner 是 UID/GID 1000，
   代码按已观察的完整 file version 绑定它；没有把 UID 1000 文件假称为 root 所有。
5. 同原 flow 顺序持有原 flow.lock 和原 global action lock，均 nonblocking。原 `Flow.bind()` 得到当前真实 R5 identity。
   当前 binding 分别与原失败例、独立 observer 比较。仅冻结合同的八处 nsfs mtime 作为观察时间处理，
   namespace dev/inode/type、进程 start、classpaths、APK/data 与普通文件时间等其他字段全部精确相等。
6. 直接调用原 `Session.installed()` → `task()` → `foreground()`，完整执行两轮。
   原 foreground package predicate 没有改；其历史错误字符串仍可能包含 Bili，但代码不据此改条件。
   结果必须等于独立 observer 的完整 scope，包括 activity 和 window token `2dfbb60`。
   当前若是 IHG、其他窗口或其他身份，立即拒绝；不会拉前台或新开 flow。
7. 复用冻结 `partial_case_core.OriginalSequence` 重解析本次真实 50 件命令/transport/intent/binding 文件：
   **六条 recorded 命令、八条 transport，其中两条是原 private foreground 查询**。
   必须正常 join、无 stderr、lease release 与 post-guard 完整；没有 instrumentation nonce。
8. 再验来源、构建、原档与 guard，关闭全部 Main authority。只允许已证明的 libffi 资源及两把原锁留到 owner 正常退出。
   新增或替换 FD 仍失败，不关闭未知 FD，不手动关闭库私有 FD。
9. 只向这个新的 proof step 写候选与副本，使用原 `write_new`，不覆盖已有文件。
   候选和新 step result 都明确 `current_action_authority=false`、`reconciliation_published=false`，并要求外层正常退出与终态。
10. parent 必须观测原 held pidfd 正常 exit 0、已关闭、无信号、无 timeout，且父 FD 身份完全恢复，才能写新的 joint artifact。
    root 仍要取回完整原 stdout 与 controller durable exit 0；只有这三层联合成功，才可准备阶段 B。

## 六条命令的闭集

两轮分别使用原方法产生以下三条 recorded 命令；第四条前台查询保持原 privacy boundary，
只留下 transport 的长度、hash、returncode 和 post-guard 证据。

| 顺序 | 原只读命令 |
|---|---|
| installed / UID | `/system/bin/cmd package list packages -U --user 0 org.droidloom.qa.successor.p8f89f253350ba2fa.r1` |
| installed / APK | `/system/bin/cmd package path --user 0 org.droidloom.qa.successor.p8f89f253350ba2fa.r1` |
| task | `/system/bin/cmd activity stack list` |
| private foreground | `/system/bin/dumpsys window displays` |

这不是可扩展的任意命令接口。请求只能等于固定 `FIXED_REQUEST`；没有包参数、命令数组、目标 PID 或自由输出路径。
所有 namespace entry 仍沿原 held R5 入口，不使用数值 PID 寻址，不增加 ADB。

## 新产物及含义

成功后新 step 内将有：原 intent/binding/六命令/八 transport、producer 原源码与请求副本、原 host proof 和 controller 原文副本、
`runtime-candidate.json`、`result.json`。源码 root 内新增 `attempt.json` 与 `owned-runtime-candidate-joint.json`。
这些文件都不能替代原 UNKNOWN；阶段 A 不创建 `reconciliations/close-and-observe-search-01.json`。

候选只证明两轮检查时的 runtime、task、helper 和完整前台 scope。
它没有重新观察树、节点、输入框、搜索页或搜索结果，也没有证明业务成功、长时、重启回归或 production readiness。

真实现场 Main 检查尚未运行。预计成功路径 stdout 只有 stager 摘要与 parent JSON；parent 内嵌 child 完整原 stdout，
没有 UI 原文、可访问节点或 window dump。
所有现有私有 bundle 保留原宿主私有路径；不要把它们或原 UI 文件复制进 Git。

## 失败、超时与恢复

- 缺少实际 host 终态、源/请求/hash 不符、已存在 step/attempt、存在 reconciliation 或 task cleanup 记录：拒绝。
- 锁争用：原 nonblocking 失败，不能等待、偷换锁或重试。
- 前台、helper、task、epoch、namespace 或普通文件身份变化：原条件拒绝，候选不能用于阶段 B。
- 命令、FD、后置 guard、文件写入或 readback 失败：保存实际失败与新 partial step，旧记录不改，不重试旧点击。
- owned child 超时只沿冻结 parent pidfd 路径处理其直接拥有的子进程，任何信号/非零/异常都会令 A 不合格。
  这不是 Main 进程回收授权；不发 Main 信号、不 killpg。
- 内层 candidate 已写而 parent 或 durable 终态失败：candidate 仍非授权，不得封 B。
  依据同一 job 的原文对账，不换 key，不重启 A，不创建另一业务 flow 绕 UNKNOWN。

阶段 B 会在 A 的真实联合结果与终态获得后单独设计封包，并再次执行相同原 runtime predicate。
冻结消费者本身不会读取 controller terminal；后续任何新 UI 决定都必须由协调器等到 B 完整实际终态后才允许。
本阶段没有 B 的源码、兼容 envelope 或未来 terminal 占位。

## 本地验证与复现

已实际完成六组必要边界控制，真实 UID/EUID 1000，stdout/stderr 原文均保留，完整 FD 身份前后相等。
控制包括实际 host 终态拒绝条件、完整前台/helper/task 对比、原 nsfs mtime 合同、真实旧 owned-child 终态 gate、
自有临时文件上的原 O_EXCL 不覆盖以及封闭请求/无 mutation 调用检查。
其中 Session 数据明确只是实际旧 observer 值构成的本地 fixture，不能叫当前 Main 观察；没有伪造 root stat。

可在本地重现源码组装与控制；这些命令不访问目标机：

```sh
python3 -B assemble_stage_a.py
python3 -B check_stage_a_boundaries.py
```

已冻结文件无需重跑或覆盖；如需修订，保留本 revision，写新的显式目录。
`SOURCE_INHERITANCE.json` 记录四个原样工具定义、八个冻结源文件与 39 个实际方法的 SHA，
以及 stager 的三个原样定义；原 source 文件从未修改。

Main Bili Accept 的独立 cell 边界、美团禁止主动位置 grant、所有完整性检查继续保留。
