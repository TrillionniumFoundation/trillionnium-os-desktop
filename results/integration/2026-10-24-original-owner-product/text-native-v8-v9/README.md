# 原文本与原生 UI 的 v8 / v9 实测

本档保存两个已完成流水的原始结果，包括失败。源快照由完整 Git tree
重建核对，不能用之后的补丁或成功结果改写本次退出码。

| 流水 | 实际源码快照 / 完整 tree | 已执行结果 |
| --- | --- | --- |
| v8 | `e3734b061c3ddca8d92ca6fe557ea753e220dc0e` / `c1cef80e818937d037891f6eaa873432bbdcbbc1` | Agentd 库 342 pass / 32 skip；原文本集成 3 pass / 2 fail；原 UI 编译暴露 AccessKit getter 可见性错误。原 `just fix` 与 Bazel 锁更新通过，锁未变化。 |
| v9 | `a81c39b9a0e705b3345c22e540d6f494031fc3d0` / `53f3d002f8f8341cb4785c8f7d29daa6df9fec16` | Agentd 库 349 pass / 34 skip；真实 Agentd/App Server 文本集成 6/6；原 UI 已编译，41 pass / 1 fail；AccessKit 53/53，Unix adapter check 通过。 |

v8 的两项文本失败来自原 Legacy `thread/items/list` 尚未实现。v9 的
六项文本集成已实际覆盖原签名文本、原信任拒绝、取消后旧身份恢复、审批
重连、大 item 历史与 900 ms 慢预览下的重复 select 取消。

v9 的专用 Legacy API 测试因 `assert_eq` 宏导入歧义未执行，`just fix`
也在该测试编译失败；UI 的一个资源测试没有调用原 `init_cx_os()`，在
读取 SDK 时钟时 panic。后续最小修复有独立提交，其验收归下一轮流水。
v8 的 standalone AccessKit 测试未配置正确的 nextest profile，属于未执行；
v9 改用原默认 profile 后才产生 53 项实际结果。

`raw-evidence.tar.gz` 保存 24 个原文成员：两组命令/退出码、16 份完整日志、
两份源码输入收据、两份 operator 终态、实际源快照清单与成员哈希。
逐成员 SHA256 和 archive SHA256 已在读取回本地后重新验证。
详见 [qualification-summary.json](qualification-summary.json) 与
[SHA256SUMS.json](SHA256SUMS.json)。

测试签名和模型服务仍是 fixture。这里不授予生产 Root、实际模型认证、
已安装产品、真实窗口输入、Android 部署或 Asterinas G2 资格。34 项 skip
包括显式 Root-only FIFO 门禁与仅由其父测试运行的 FIFO child，不计为通过。
