# R10 交付主干同步：保留 #198 的独立来源与原始资格

本次报告交付以 main `7e859b98c58053b88ea2baabc3e5f645fd38dca5` / tree `354adb549b064c78477932ca943309694eb54356` 为产品基线。该主干于2026-10-19 **04:29:28 UTC** 合入 [PR #198](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/198)，parents 为 `71ce079c3218a8692476e4113b60c9d2c0d2a172` 和 `dafa1eba79cb1e17f880b5f0c5d57a80510d5d68`。原[API观察](api-observation.json)包含37路径和PR正文；API正文的声称与实际artifact独立审查分别处理。

## 1. 报告整合与旧交付

[源码边界检查](source-integration-review.json)以当前主干6,426个Git对象路径为基线，逐一核对报告外6,424个路径；产品、工作流、测试、文档及既有证据的blob/mode全部保留。37个主干变化中只有`docs/INDEX.md`与本报告编辑范围相交，该页保留新A04入口并协调R10摘要；A06工作流直接采用7e的精确blob。根README仍为0字节，原R9两个目录74文件及e15完整STATUS历史保留。

此前固定交付 `bc309bebba52622dd165a657447306a2cf32928e` / tree `477f6e9fdb9be7a15c94f9d534eb8ec033ecc47b` 已有一次独立Git QA成功。它的[原收据](../../review/pre-main-sync/independent-receipt.json)、[原checker](../../review/pre-main-sync/receipt-reviewer.py)、[原manifest](../../review/pre-main-sync/delivery-manifest.json)与[原模块delta](../../review/pre-main-sync/module-documentation-delta.json)按原字节归档，**只证明旧tree477**。新的[405条目保留/升级清单](../../review/main-sync-entry-preservation.json)明确区分冻结producer证据与更新的摘要/helper；当前交付由新的最终Git审查绑定，不把旧QA改记为新树成功。

## 2. #198 源码改变

实际生产改动为五个socket/message flags/recvmsg文件；现有CPU owner、os-control、HOS2及FileTable/exec helper未改。接收时的`MSG_CMSG_CLOEXEC`沿原ancillary写入链传递，`FileTableEntry`在被插入表之前构造最终flags；普通接收不继承发送端descriptor flags。实现及独立27项profile见[SCM_RIGHTS/CLOEXEC手册](../../../../../tests/workloads/linux/SCM_RIGHTS_CLOEXEC.md)。A04的[164行handoff](../../../../../docs/agents/handoffs/A04_LINUX_HEPTA_ELF.md)仅更新两行，保留完整四ELF/rootfs候选边界；本次不改写它们。

源码显示插入时原子设置flags，现有exec在原表write guard下清理CLOEXEC文件。27项fork/exec场景验证继承和清理语义，**不是并发exec竞态压力测试**。FD限制、RLIMIT_NOFILE、部分失败回滚与copyout-fault语义仍需分别完成，不能从该五文件修复推出这些条件已闭合。

## 3. 已直接取得的普通 CI 产物

[独立审查](independent-pr198/pr198-source-artifact-review-02.json)于04:58:44.913–04:58:46.292 UTC读取并核对固定head `dafa1eba…` 的源码和实际ZIP；`blocking_findings=[]`。其[原member清单](independent-pr198/pr198-a06-members.json)和[19文本文件冻结清单](independent-pr198/pr198-text-review-frozen-02.json)保持原字节，不运行下载到的程序。

| 项目 | 本次实际来源和核对结果 |
| --- | --- |
| Actions来源 | [run39198594211](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39198594211)，attempt1，job117886620994；04:15:56–04:22:23 UTC，14steps成功，精确head观察4checks成功。它不是另一次post-merge执行。 |
| 实际ZIP | [artifact12162813771](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39198594211/artifacts/12162813771)，23,402,372字节，SHA256 `bce2548f17c9b9d22bfc10e398999dacea07e2c8942f497a87435c3d38e76545`；93成员/56,623,284解压字节，全部成员size/SHA/CRC检查通过。 |
| 当前同ELF | `9b80de2bb994d86d32592f5c2a4824c8406b41c1aedc74df299755c807065fb1`，808,328字节；Linux **6.17.0-1022-azure**与新内核guest均27 PASS，probe exit0。 |
| 当前普通内核 | `1145311a1335b866196019dfeea5937a86d4cbc4ff1efb222e8a229137b3737b`，8,395,328字节；x86_64/QEMU8.2.2/TCG/q35/单核512MiB，guest raw33，约0.916秒。 |
| 固定输入与initramfs | Git source6,426路径/103,947,441字节，三个source snapshot SHA `8757e432c2a04cdbd57dc7d68117fb4bf3d10ed3635aa5617c1ac4ce4f1ef356`；25→26个initramfs成员，其余成员内容和metadata精确保留。 |
| 本头G1回归 | 此次原串口另有core179、OSTD221reported含3softskip，下界397；十个G1测试和14个QueryAbi marker均核对。原收据共9个guest调用，含新增SCM客体；不能与旧1c八客体相加为一次运行。 |
| 配额范围 | 收据为1vCPU0.800%/1.000%、2vCPU0.955%/1.000%；本次仅核对原收据与serial身份，没有重复执行旧配额oracle或扩展为一般SMP资格。 |

三个全树snapshot只覆盖**普通product/QueryAbi区间，止于新增SCM guest之前**；SCM runner另外绑定自身helper和客体输入，这不等于最后SCM之后又取得一份全树Git快照。原G1-a完整包仍以1c/tree2b为自身资格来源；上表是#198的独立新运行。

## 4. 保留不同 ELF 的历史 RED

Git中[原始RED材料](../../../../compat/2026-10-19-scm-cloexec/README.md)保留probe `0723be7d0ba01f6a94fd4766e4aaf98bc6590de4bbfe431455aefcba8e8eeb56`（808,304字节）与Linux **6.18.55**参考。该ELF在Linux上27 PASS，在旧普通内核 `f8785d9371f27b1f5e9ccd40da66ea25823ca50bfc7c431a89f20f88a45c4681` 上3 PASS/24 FAIL，27项全部执行；probe exit1，raw QEMU33。raw33只表示正常退出方式，不能覆盖probe失败。

PR正文另称历史0723 ELF已在新内核GREEN；这次取得的ZIP只提供9b80 ELF在Linux与新内核的同输入成功。Git历史manifest仍保留其当时pending字段，**本审查未独立核实0723在新内核上的另外那次GREEN**。这项原件边界不是新实现阻塞；也不能将0723的RED与9b80的GREEN拼成同一ELF修复证明。

## 5. 文本交付与审查边界

本目录只追加19个冻结文本文件和阅读/整合收据，共653,397字节的原19文件已逐source前后与副本比较，见[复制收据](../../review/pr198-text-review-copy.json)。完整23.40MB新ZIP不进入R10交付Git树，也不新增分片；读者通过上述原Actionsartifact获取，再按原member清单核对。原有72个二进制和57个运输分片保持字节，本次不改写旧14份archive内部内容。

原精确解码job日志是`a06-job-117886620994.original.log`；较早`.log`副本多一个末尾LF，二者原样保留，差异见[日志来源](independent-pr198/job-log-provenance.json)。审阅器第一次误按单行读取原多行ktest记录，原脚本/失败收据保留，[解析修正](independent-pr198/review-parser-correction.json)只改审阅器，不属于产品失败。交付源码checker也保留一次错误拒绝既有Git symlink的[原失败](../../review/main-sync-checker-first-attempt.json)，修正后直接绑定mode120000与原symlink target字节，没有改产品。

本次#198结果不授予完整Linux兼容、Debian13四ELF/rootfs、Hepta效果/K↔D、通用IRQ/SMP、ARM内核或实体/移动设备资格。Hepta状态另以[04:44–04:45有界快照](../../hepta-final-status/README.md)为截止，三PR均Ready/open/unmerged/blocked；之后不再扩写本轮范围。
