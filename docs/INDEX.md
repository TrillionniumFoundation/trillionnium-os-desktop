# 开发文档入口

文档集修订0.3，2026-10-16。根README.md保持0字节；开发内容只在docs与明确源码/支持目录中。真实实现/测试状态统一见 [STATUS](STATUS.md)。

## 共同原则

新Rust内核管理硬件，Hepta沿现有单一智能/工具主链成为用户态原生系统服务。Linux/Android是兼容生态，VM明确标记补缺。模型不持根权限，内核快速路径与本地恢复不等待模型/远程控制。

本文中的契约和算法是实现规格，不是运行证据。source pin、格式检查、规格模型、codec、内核/硬件与产品验收分层报告。已有授权范围内自动执行，不增加重复审批、证据服务或空壳workflow；权限、资源、结果和恢复检查属于实际运行机制。

## 阅读与实施顺序

| 文档 | 主要内容 |
| --- | --- |
| [PROJECT](PROJECT.md) | 原生定义、profile、W0–W5应用与交付 |
| [ARCHITECTURE](ARCHITECTURE.md) | 完整Asterinas派生、真实源码接合、同对象与并发 |
| [NATIVE_ABI](NATIVE_ABI.md) | HOS2五操作、启动交接、全局预约、历史观察与退役的唯一规格 |
| [HEPTA_INTEGRATION](HEPTA_INTEGRATION.md) | 真实源码符号/profile、状态owner、控制器 |
| [SECURITY_AND_RECOVERY](SECURITY_AND_RECOVERY.md) | TCB、熵/时钟、S0/S1存储、更新与故障 |
| [LINUX_COMPATIBILITY](LINUX_COMPATIBILITY.md) | 必需接口、rootfs和应用交付、差分 |
| [ANDROID_COMPATIBILITY](ANDROID_COMPATIBILITY.md) | 产品/VINTF/MAC/Binder/页大小与代理边界 |
| [HARDWARE_AND_DRIVERS](HARDWARE_AND_DRIVERS.md) | DMA/队列/复位与提前风险调查 |
| [DESKTOP_UX](DESKTOP_UX.md) | Rust/Wayland/分域Xwayland/Android桥 |
| [ROADMAP](ROADMAP.md) | 明确M0/M1/M2依赖及下一次真实实现 |
| [VALIDATION](VALIDATION.md) | 判定器、注入层级、22项审计映射 |
| [DECISIONS](DECISIONS.md) | 默认路线与重议条件 |
| [STATUS](STATUS.md) | 本轮实际执行、未完成项 |
| [SOURCES](SOURCES.md) | 一手来源与固定快照 |
| [upstream-lock](../support/upstream-lock.json) | 已核查源码与参考资产、显式缺失构建输入 |

每次后续改动直接修改对应契约和状态，不重复复制ABI字段或完成度。旧仓库重建历史保留在Git初始提交；不混入永久产品要求。

本轮新增[恢复规格场景](../tests/spec/test_recovery_contract.py)、[固定字节样本](../tests/golden/hos2.json)与[执行结果](../results/spec-recovery-v03.json)。它们不是Rust codec或内核实现。未修改文件保留其原小版本，避免仅为版本号全量重写。

## 多 Agent 并行开发

[并行开发执行方案](agents/PLAN.md) · [独立可复制的各 Agent Prompts](agents/PROMPTS.md)。职责与验收以这些文档为准，不改变现有内核实现状态。
