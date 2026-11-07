# Clock 到时服务候选：当前证明与待验证事项

候选 APK 已实际构建、同证书签名并完成完整 DEX 与 APK payload 对比。当前尚未安装，也尚未通过到时冷启动复验；`expiry01` 的实际失败保持不变。

## 为什么改这两处

原始 60 秒实验的 AlarmManager 记录显示，`com.android.deskclock.action.TIMER_EXPIRED` 在预定到期时间触发了 1 次 wakeup/alarm。正常移除 Clock task 后，框架因 `remove task` 结束原 Clock 进程；到期时未观察到新的 Clock 进程启动，TimerService 的记录为 `app=null`。直到清理过程重新打开 Clock，计时器仍为 RUNNING，画面已经显示负数。实验在固定观察窗口内失败，之后只用实际 UI 暂停、删除本轮唯一计时器，最终计时器和秒表均为空，两次 owned task 均正常移除。

这些是实际现象，不能单凭 `app=null` 或 `mAllowStart=DENIED` 认定某个具体限制已经被执行。完整证据分别保存在 `clock-timer-expiry01-result.json`、`clock-expiry-diagnosis01-result.json` 以及私有原始日志；公开失败摘要位于 `publication-expiry01/`。

实际已安装 Clock 的 `TimerModel.updateAlarmManager()` 在创建和查找待取消的到时 PendingIntent 时都使用 `PendingIntent.getService`。实际 `TimerModel$Companion` 用 `setExactAndAllowWhileIdle(ELAPSED_REALTIME_WAKEUP, ...)` 调度它；实际 `TimerModel.updateHeadsUpNotification()` 只有在 TimerService 已经进入处理、形成 expired 集合后，才调用 `Service.startForeground`。

Android 的 API 契约规定，`getService` 对应普通 `startService`，`getForegroundService` 对应 `startForegroundService`。后者自 API 26 提供，而此安装包的实际 minSdk 为 37，因此本次针对固定安装包的改动不需要旧系统兼容分支。官方说明：[PendingIntent](https://developer.android.com/reference/android/app/PendingIntent)、[启动前台服务](https://developer.android.com/develop/background-work/services/fgs/launch)、[Android 8 后台执行限制](https://developer.android.com/about/versions/oreo/background)。

## 与此设备实际框架的对应关系

`clock-service-start-policy01.json` 导出了此设备现装 `services.jar` 对应的完整关键方法。JAR SHA 为 `f33987e633e476f47ea043af3f7fb94907fd2431fa2b5b49df84cb586bce5c50`，其中 `classes.dex` SHA 为 `70975dd40f27f01f35ff254bd7cbb8a1683c6255aca515ffe162f35df8c35d1c`。

实际 `ActiveServices.startServiceLocked` 的长重载把 `fgRequired` 作为参数。普通启动检查的入口条件为：

```text
forcedStandby || (!isStartRequested && !effectiveFgRequired)
```

满足条件才进入 `getAppStartModeLOSP`。非允许结果可在 `startServiceInnerLocked` 之前返回拒绝的 ComponentName 或 null。对前台服务请求，实际框架另有 foreground app-op 检查，并使用 `isBgFgsRestrictionEnabled` 与 `isFgsAllowedStart` 检查准入；app-op 允许、没有 forced standby 时，前台路径可避开上述普通冷启动门槛。

这里的前台限制开关读取 CompatChanges `0xa2c30a7`，该方法中没有直接比较 targetSdk；不能仅凭 Clock targetSdk 30 宣称它一定被豁免。`getAppStartModeLOSP` 的 `alwaysRestrict=false` 路径会调用 `appServicesRestrictedInBackgroundLOSP`，不能把相邻的 `appRestrictedInBackgroundLOSP` 当成同一个分支。源码能证明候选改变了相关入口，不能替代真实 A/B 到时实验。

随后从同一已校验完整 AMS 类补齐了 `appServicesRestrictedInBackgroundLOSP`，其完整方法 SHA 为 `448fa5f5c2e5fe9c9a62aef48f02ea2bcc229896dc2ffdf0c0be1b3ad78cec37`：persistent package、background UID allowlist 或 device-idle allowlist 任一符合即返回允许，否则再调用 `appRestrictedInBackgroundLOSP`。后者对 targetSdk≥26 返回模式 2。补充源码位于 `service-start-policy-addendum01.json`。没有逐分支运行时 trace，故仍不把可能的路径写成已经证实的单一根因。

## 具体修改和构建结果

`TimerModel-foreground-service.patch` 仅替换两处方法名，分别覆盖取消路径与创建路径。Intent、request code、flags、寄存器、timer ID、时间计算、异常覆盖及其它方法全部保留。同一种 PendingIntent 类型必须同时用于创建与取消；更新前必须确认没有活动计时器或秒表。

| 项目 | 真实结果 |
| --- | --- |
| 原 APK | `ded49b00e5045bdd184c2a4f09b1b8650ce8f708134ac9f0f8c4cf0594bb0fae`，7,449,572 B |
| 候选 APK | `cc7eece9d0429267d1950f0ca9287b041493bc5c05602ffc2119e1866381fb73`，7,593,129 B |
| 新 TimerModel source | `65d59b45037fa51534698f8d0715583945307693ac707c8f24612996ee7a810e` |
| 全 DEX 对比 | 2,941 类、19,738 方法；仅 `updateAlarmManager()` 的指令 32、40 变化 |
| 其余结构 | 类 metadata、方法集合、控制流及异常覆盖保留；0 处非目标语义变化 |
| APK payload | 1,281 个非签名成员；仅 `classes.dex` 字节变化 |
| 签名 | 原包与新包实际同证书 `a40da80a…`；新包 v3 验证通过 |
| 对齐 | 签名后 16 KiB 验证通过 |
| 资源控制 | CPU 20/21，2 GiB 上限，0 swap；实际峰值 688.3 MiB、15.1 秒 |
| Android 状态 | UID 10063、通知 true、原 disabled alarm IDs 1/2 内容 digest、全部 prefs 字节、R16 epoch 前后一致 |

完整 DEX 重新组装会改变 DEX 布局和相关编码，不能表述为 APK 只改了两个字节。严格结构比较器会保留指令、标签目标、异常覆盖、注解、方法集合和类 metadata；仅规范化已声明的调试信息、隐式 false 字段与 const-string 宽度。

真实构建 job 为 `1a1ab802558-fc05-4e57`，终态 succeeded/0、output complete/durable。第一次 MCP 回执超时原样保留；随后按工具契约使用完全相同的请求和 idempotency key 对账，得到该原逻辑操作的实际 job。没有更换 key 或另起第二个构建。

## 更新与复验边界

`clock_install01.py` 单独提供默认 inert 的安装、只读对账、精确原 APK 回退模式。安装必须持有既有 UI 动作锁和冻结的 R16 namespace/session，验证候选与原包同证书，备份当前实际 APK，使用 alex 的现有 u1000 Main 入口完成唯一安装调用。前后核对 UID、CE/DE 目录身份、权限、两条原 alarm 完整内容 digest、空 timer/stopwatch、prefs 字节、音量/铃声设置和当前 task 集合。未知回执只读对账，不自动重试或回退。

只有在 root 审阅并完成这次 Clock-only 更新后，才用新的唯一 60 秒计时器重做相同冷后台场景：Start 后正常移除 own task，验证到期时实际进程/服务和状态转换，再依据本轮唯一 expired 集合、实际窗口与真实控件处理提醒和清理。原始失败不会被覆写。声音输出、锁屏、Doze、重启恢复和整个 Clock 的 production readiness 仍须各自的实际证据。
