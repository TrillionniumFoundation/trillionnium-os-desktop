# 专属执行主机入口只读复核

基线 HEAD：`e932e49191db61bb4b95d4dbbb891e4793908219`。扫描时间：`2026-10-17T01:08:09.080697+00:00` 至 `2026-10-17T01:09:07.629421+00:00`。所有 shell 调用均为 `/bin/bash`、`login=false`。

限定结论：在本 checkout 已检查的受版本控制项目文档与配置中，未找到可据以操作的、已经授权且可用的 KVM 执行入口或第二台专属主机入口。此结论不证明仓库之外不存在资源，也不将“用户已授权现有项目云环境”解释成另一个未记载主机的接入资料。

实际依据：

- 5 个 workflow 的 6 个 job 均为 `runs-on: ubuntu-24.04`，没有 self-hosted 或专属 runner label；普通 runner 配置本身不证明 KVM 能力。精确路径/行号见 `references.json` 前六项。
- `support/hardware/rtx4060-lab-profile.json:3` 为 `candidate_not_detected_or_authorized_on_accessible_hardware`；18–24 行物理主机字段为空，`verified_isolated_machine` 为 false。
- `support/build/repro/README.md:71–77` 明确区分实际 host identity 和嵌入的 build identity，后者不能用作第二 host 证据。
- `support/vmm/GATES.md:6–16`、`support/hardware/DECISION.md:5–9` 是设计/既有容器观测；本轮没有重做 `/dev/kvm`、AF_UNIX 或任何运行能力测试。

审阅读取 62 个主要 docs/config 文件，另读取 21 个已受版本控制的 A02 交接 metadata JSON。第一轮 scan 的“排除全部 historical evidence”文字过宽：实际 glob 仅排除 `support/build/evidence/**`，nested handoff metadata 也被读取；这些文件没有 host-entry 命中，不用于授权判断。完整输入文件 SHA256、精确引用、原脚本、原始 stdout/stderr 和实际 exit0 调用回执均已保存。

没有搜索凭据、密钥、云账号或未跟踪的宿主配置；没有操作 VM、运行 Cargo、修改仓库或旧证据。
