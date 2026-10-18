# A10 CI 自动执行原版 Shell 捕获契约

本轮审查发现默认 A10 workflow 尚未调用新加入的 8 项 Python 捕获契约测试。已在现有 process guard 步骤后接入独立命令，启用 `set -euo pipefail`，将原始输出保存到 `original-shell-contracts.log`，由既有 `always()` artifact 步骤上传。仅改 workflow 与复跑说明两文件，共 11 行；没有改生产 UI、Session、原版 gate 或捕获判定器。

实际提交为本地 `632f5f0b27bc4c051f1b13dbb162e3c7cb9727ef`，同树远端 [`9a9c4fac92c5b3e5595845efbea72efe869763b4`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/9a9c4fac92c5b3e5595845efbea72efe869763b4)，tree `2486e578a802b30c396f1910a6e7d6c42a70b8af`。

已从该提交的 workflow 提取 run block，检查与预设逐字一致，然后在本地真实执行一次，结果 **8 passed / exit0**。`execution/receipt.json` 记录源码前后干净且同一 HEAD/tree、六份输入摘要相同，原始进程输出与 tee 日志一致。命令包括真实一次性子进程的父死 SIGKILL 与回收检查，其余是明确的契约输入；没有启动原版 Agentd、Session 或 Shell。

```bash
set -euo pipefail
mkdir -p "$RUNNER_TEMP/a10"
python3 -B -m unittest discover -s tests/ui \
  -p 'test_original_hepta_shell.py' -v 2>&1 | tee "$RUNNER_TEMP/a10/original-shell-contracts.log"
```

[原始 tee 日志](execution/runner-temp/a10/original-shell-contracts.log)、[实际收据](execution/receipt.json)、[执行计划](execution/execution-plan.json)和前后源码快照均按原字节保留。原始收据 SHA256 为 `b0fd52967c4db36136cd512ad1fee1a0f62c7e8a3e62432f86b6b2e05a5d9e57`，日志 SHA256 为 `0e897af3e9aaf7af2a6d9e6eb3e9051075ff89f4f985ceaa0712a2c2edd7cf85`。`execution/SHA256SUMS` 保留原始文件清单，本目录 `SHA256SUMS` 另外覆盖完整归档。

这是新 CI 步骤的精确本地执行证据，不声称 GitHub 已运行该提交。此前 `84e08165` 的 ARM 通过和 A10 队列状态各自属于旧工作流来源。这个步骤不授予窗口像素资格；实际两轮原版六阶段与 13 张 PNG 见[独立原版 Shell 归档](../2026-10-17-original-hepta-shell/README.md)。
