# 2026-10-23 审计实施验收

每份 publication 固定实际源码、原始输入与逐文件摘要。原始大型映像、ELF、构建目录保留在其记录的执行目录；仓库保存原收据、清单、串口、过程日志与限定测试截图。压缩日志解压后与记录的原 SHA-256 相同。不同来源的通过不相加为当前整树的统一验收。

| 新执行 | 实际来源 | 结果与边界 |
| --- | --- | --- |
| [完整内核四套](full-ipc-0187/publication.json) | OS `0187bd578f6786c40c812c13976e4889a1aba835` / tree `335007e4f94114c6a26506d9448faf0d43c4245c` | 原未过滤 core303、allocator20、ML15 全通过；OSTD229 报告通过，保留原 TCG VMX 软跳过3。四个 QEMU33、原300秒期限。另有[同 ELF 实际 KVM229、零跳过](ostd-kvm-0187/publication.json)。[首次稀疏缺源拒绝](full-ipc-0187-preflight-failure/publication.json)保留。 |
| [完整 Linux32 与 ordinary](full32-0187/publication.json) | 同一 OS `0187bd57` | 新 bundle、新实际 UID65534 Linux chroot 参考32/32、新 ordinary 构建/启动18标记、新 native32/32。ordinary ELF `16d59287f0d228e0032520a36f876aecfeda9190d215eec61bce68bb03988c52`；全部8223 tracked 输入前后不变。不使用旧980参考收据。 |
| [原生 runtime 与 store](native-runtime-0187-b3/publication.json) | OS `0187bd57` / 原 Hepta `b3d3f2d4b01f123d7ac17575c27fb54d00094f7f` / profile `e28c192dae36397526bfb2f765b91090de46945f` | 新原构建器生成 kernel receipt，ELF 同上。原未改生命周期8/8、原 store SIGKILL/WAL/双进程CAS10/10、两个QEMU33。明确复用未变化的原 store userspace build receipt；没有把旧内核收据改标签。尚无生产恢复 writer、模型任务、资源效果、完整F1或G2。 |
| [完整 A10 Linux-host](a10-f3d54e5b/publication.json) | OS `f3d54e5b4d450deed2f2d21101321a6cf2f6d8b8` / tree `3b597e454280b822b6d3be109c02afcced5ed7c2` | 原工作流11个执行体全部退出0，Rust1.88、严格Clippy、原Session、实际X11像素、AT-SPI、Weston、共享presenter、进程合同与最终源码/锁清洁均通过，146.849秒。复用构建缓存，未声称冷构建。尚不包含后续Session/Shell重启改动、完整IME、生产Notes writer或Asterinas图形。 |

新整合 `3fac0fbe9ed0ae22fc6117e1aa089bd4e3a50a92` / tree `28b34e8fd88ea95e187016f6387a514a787a9b09` 接入 Session 重启保留原 intent ID、Shell 重启从原 owner 恢复导航并以 Unknown/status-only 查询。[完整原 A10 十一步再次通过](a10-restart-3fac0fbe/publication.json)，244.111秒、同一强制像素及最终源码/锁清洁要求。仍需独立完成原 host authority 的可写性检查、历史后台核对/容量语义和生产持久 Notes；已有 renderer 测试通过不关闭这些缺口。

A10 前三次运行均保留总失败判定：[01 长临时路径超过 Unix socket SUN_LEN](a10-efd62111-failure-01/publication.json)、[02 跨 UID fixture 无法穿越0700临时父目录](a10-efd62111-failure-02/publication.json)、[03 十一步全成功但最终清洁检查拒绝生成的pyc](a10-efd62111-failure-03/publication.json)。第三次的字节码身份在原 observation 中保留；当前工作流为六个隔离 Python 入口加 `-B` 后，重新执行完整门禁。原断言、期限与最终清洁要求未放宽。

早期 `7d8906ef` runtime、`10dae5ea` watchdog/只读、`98048e94` ML 与 `f89023ac` 手机 APK 均按原目录保留。目录存在或文档补充不把它们转授当前完整组合。生产授权、认证 current cut、原 writer/outbox 持久 CPU K↔D、全局资源恢复和物理设备资格仍未闭合。
