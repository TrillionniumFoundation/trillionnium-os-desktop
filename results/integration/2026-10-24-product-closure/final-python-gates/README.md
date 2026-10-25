# 最终源码的本地 Python gates

固定 Desktop：`0a268d8928d76682a59c8cc0be88428845f40ce3`，tree `d7c0d61a1519db8f4b0a7178b9f6867f85719b48`，即 Draft PR #262 已发布代码树。全部命令 cwd 为 `/workspace/scratch/159b66073956/repos/desktop-product`；Python 3.12.14，UID/EUID 0；使用 `PYTHONDONTWRITEBYTECODE=1` 和 `python -B`。每个 `.json` 回执记录实际 argv、cwd、时间、退出码、准确计数、源码前后状态及原始合并 stdout/stderr 的摘要。

## 实际结果

| gate | 执行模式 | 结果 | 原始回执 / 日志 |
| --- | --- | --- | --- |
| `tests/spec` unittest discover | 普通 Python | 53 passed，0 failed/error/skipped | [receipt](spec-normal-sandbox.json) / [log](spec-normal-sandbox.log) |
| 同一 spec suite | `-O` | 53 passed，0 failed/error/skipped | [receipt](spec-optimized-sandbox.json) / [log](spec-optimized-sandbox.log) |
| `tests/ui/test_product_source.py` | 普通 Python | 10 passed，0 failed/error/skipped | [receipt](product-source-normal-sandbox.json) / [log](product-source-normal-sandbox.log) |
| 同一 product source mutation suite | `-O` | 10 passed，0 failed/error/skipped | [receipt](product-source-optimized-sandbox.json) / [log](product-source-optimized-sandbox.log) |
| `tests/ui/verify_product_source.py` | 普通 Python | passed，exit 0；此项不是 unittest 数量 | [receipt](product-source-verify-sandbox.json) / [log](product-source-verify-sandbox.log) |
| Android `test_device_organ.py` | 普通 Python | 24 passed，0 failed/error/skipped | [receipt](android-device-organ-sandbox.json) / [log](android-device-organ-sandbox.log) |
| `support/ui/product/test_*.py` discover | 已授权本地主机执行 | 65 passed，0 failed/error/skipped | [receipt](product-tools-authorized-host.json) / [log](product-tools-authorized-host.log) |

共7条被接收的 gate 命令，其中6条 unittest 命令共215次测试执行。普通/`-O`重复各自同一组方法，不能称为215个不同测试。没有扩大到别的 Android 模块或附加宽泛测试。

产品 suite 的第一次 sandbox 执行也完整保留：[receipt](product-tools-sandbox.json) / [log](product-tools-sandbox.log)。该轮65项中63 passed、2 errors：测试自己子进程时 `/proc/52/stat` 不可见，以及本地 UNIX socket `bind` 被 EPERM 拒绝。按已有授权，仅将原65项完整 gate 在本地主机沙箱外执行，测试和源码均未改动，最终65/65通过且无skip。没有把失败轮删掉或改成通过，没有把真实身份检查mock掉。

## 源码与锁未变

每次执行前后 HEAD/tree、tracked状态、双锁摘要、全部既有未跟踪文件的内容摘要均一致。tracked源码干净；开始时即存在3处 `__pycache__` 目录共12个未跟踪文件，原样保留且内容不变，没有为了测试清理或改写它们。这个事实记录在回执中，不能将该目录描述为完全无未跟踪文件的 clean checkout。

| 锁文件 | 前后相同的 SHA-256 |
| --- | --- |
| `ui/Cargo.lock` | `1454b3ec327ed5cb2bd77c1c483c28130b43c8b5ee7e771f94f8a825e8f3f3ed` |
| `services/hepta-session-host/Cargo.lock` | `5e648029cd086565a831637985e7d3a43f0fb8ac726a09eaf39b72e550bcbc05` |

source verifier 确认 Hepta `22e87e0dd6560a7b925e716a33011378ae07a9a2` / tree `7e376f5d3509cf38e13b513ca2b87d9eecd7dc47`，7个manifests、29个Hepta声明、UI锁154个和host锁149个原Hepta packages。输出仍明确 `runtime_tests=not_run_by_this_tool`、`production_authority_verified=false`。

## 范围

此包验证主机Python逻辑，包含测试自建的临时文件系统、子进程、pidfd和UNIX socket。未调用远程Runtime、未修改产品源码/锁/部署、未碰生产设备，也没有提供原Root/AppServer retained authority或Pocket4原签名/stricthelper/peer资格。fixture ELF与打包测试不等同实际安装UI的生产认领。

完整机器汇总见 [summary.json](summary.json)；报告E14的单独更新建议见 [E14-update.md](E14-update.md)。本包独立于之前35文件的`closure-evidence-v1`，不重写旧inventory、日志或归档摘要。
