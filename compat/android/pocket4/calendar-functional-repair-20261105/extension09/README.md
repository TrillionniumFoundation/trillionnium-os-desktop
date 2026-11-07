# Calendar09 菜单类型修复与实际 ART 证据

已安装 Calendar08 的首次启动在 `AllInOneActivity.onOptionsItemSelected` 触发真实 VerifyError。菜单 hook 将同一寄存器分别用于 CalendarController 和 Long，在分支合流后被验证器视为 Object。Android 实际创建 task963 后因该异常结束并移除任务；基线 task851 与八张 Provider 表的零行状态恢复，旧 failed/unknown 回执保留。此轮没有事件、日历创建或正常关闭资格。

Calendar09 将时间寄存器先设为 null，并将控制器放在独立局部寄存器；两条路径合流为 null/Long。实际构建比对了 445 个原类、2327 个方法，与08只此方法变化；classes2.dex 和所有其它非签名 ZIP payload 保持原字节。原91项 Java 边界检查全部通过，同证书 v3 和16KiB对齐验证通过。第一次 stage 的归档断言失败独立保留；随后新的 create-only source09-v2 完成真实构建。

使用 Pocket4 已安装 ART、原52项 boot classpath、原 boot/APEX 和同 Main epoch，在独立2GiB/0swap/CPU20–21单元对候选 APK执行 verify，并启用 hard/soft verifier error 中止。实际65个新增或修改类全部存储状态为 Verified；所选 app class dump 共199个类，没有未验证状态。末态资源限额与前置相同，内存峰141,963,264字节，max/oom/oom_kill均0。前后输入/boot/APEX/已安装08未变，两个固定cache目录未观测到持久元数据变化；这不是所有瞬时写入的追踪。

这是源码、构建和隔离 ART 资格，安装09及Calendar业务验收在后续独立回执中记录。提醒/Snooze宿主用户操作、重复事件与其它业务范围仍需真实验收。没有 whole-app production-ready 结论。

## 来源与发布边界

本增量依赖 public-extension08/SOURCE_MANIFEST.json（5b7c02f1c9b47cfe6dc0ea0d7b487439968fa3f5ddc046911cdaf8738c4d2894）及前序源码。完整 source09/SOURCE_PINS.json列出20份构建输入；此处只收入09改动，其它源按08精确输入复用。没有发布APK、DEX、签名私钥、请求base64、原始UI截图、完整proc/env或用户日历内容。
