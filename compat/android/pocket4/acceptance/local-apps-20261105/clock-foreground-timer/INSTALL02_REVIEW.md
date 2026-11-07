# Clock install02：独立差异审阅

2026-11-05 12:04:53.540596–12:04:56.657626 UTC，唯一实际 Clock 安装调用明确返回成功，当前 APK 实际 SHA 为 `cc7eece9d0429267d1950f0ca9287b041493bc5c05602ffc2119e1866381fb73`。原安装器结果仍为 **POST_INSTALL_STATE_DIFFERS**，没有覆写为 INSTALLED_VERIFIED。

该严格判定来自两个已查明的非 APK 差异：

- `READ_EXTERNAL_STORAGE` 仍然 denied；仅在已有 `RESTRICTION_UPGRADE_EXEMPT` 等 flags 上增加 `RESTRICTION_INSTALLER_EXEMPT`。没有读取权限被授予，通知权限仍 true，`USER_SET` 及其它 runtime permission 状态与 flags 原样。
- Preferences 的 `intent.extra.alarm.global.id` 从 119 增加为 120。安装器未保留原 XML 全文，但安装前整文件 SHA 已独立记录。把实际捕获的 231 B 安装后 XML 中这一个整数替换回 119，构造出的全文件 SHA 恰好等于安装前值。这证明整文件其余字节相同；它是离线重构，不伪称原始 XML 留存。复算脚本为 `verify_prefs_reconstruction.py`，没有任何设备写入。

完整前后快照的其它受控项目完全相同：UID 10063；CE/DE 目录 device/inode/owner/mode；firstInstallTime；原 disabled alarm IDs 1/2 的完整内容 digest；alarm instance 为空；timer/stopwatch 为空；所有已观察音量流及铃声设置；任务集合转储 hash；R16 epoch。没有外部音频变化，没有 app data 写命令，没有重装、counter 恢复或 rollback。

该审阅允许继续针对新 APK 进行原 60 秒冷后台功能复验。它不把“所有权限 flags 或 preferences 字节未变”计为通过，也不构成 timer expiry、音频或整 App production readiness 的通过证据。原始 failed/1 终态、实际 ACK、exact diff、离线重构证明分别保留。

第一次 install01 的 signer symlink 前置失败同样保留；它发生在 install_once 之前，为 NOT_DISPATCHED、零实际安装调用。install02 使用已核验且实际执行的 canonical signer 后完成本次唯一真正的升级。
