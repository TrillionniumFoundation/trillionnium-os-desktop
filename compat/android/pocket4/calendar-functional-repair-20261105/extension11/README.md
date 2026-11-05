# Calendar11 合法日历回执修复、精确清理与实际升级

Core11 在 Calendar10 上实际通过 New event 和显式 Create local calendar 创建了唯一 LOCAL 日历行，但编辑器随即显示无法确认写入并阻止继续。没有保存事件。原回执为 failed/exit1，task974 正常关闭，calendar1 暂时保留，其他七张表为零。原回执的最终检查在非零日历计数处停止，因此没有填入最终 guard/task-set 成功字段；独立只读对账随后确认同 Main、只有 task851、无继续写入，不能把这份后证回填成原流程成功。

## 产品修复与验收器修正分别取证

实际 CalendarProvider 的 Calendars 插入返回 `ContentUris.withAppendedId` 作用于原始带 sync-adapter 查询参数的 URI。Calendar10 复用了禁止所有查询参数的通用回执检查，导致插入已提交后抛出未知结果错误。Calendar11 只增加日历专用 `calendarId(receipt, expectedInsertUri)`：绑定本次内部构造的 LOCAL collection URI，要求返回查询字符串与本次提交逐字相同、精确三个参数且无 fragment，再复用原严格 authority/path/正整数 ID 校验。事件和通用回执检查保持不变；完整 owner/ID/name/label 读回与未知结果禁止重试仍保留。

验收器还有独立编码问题：相同完整 owner、ID 与 `NOT EXISTS(Events)` 条件，用 `account_name=Droidloom+local+calendars` 查询得不到行，仅把空格编码改成 `%20` 就得到确切 id1。两条都是同一次纯读对照，未删数据。新的单次清理只采用这个已证编码，沿实际 Provider 事务链在最终 SQL DELETE 再评估完整谓词。19:07:25.102493–19:07:28.185376 UTC 实际一次删除成功，八表归零，task851、App/Provider/权限及 Main 前后相同。正常 Provider 删除可能为同一个未注册的 LOCAL account 尝试内部 unsubscribe/scheduleSync；控制器没有调用外部账户或同步 API。

## 构建与实际 ART

真实 SDK/DEX 增量构建通过116项 Java 检查，其中37项为回执边界。与实际已安装10比较，原445类2327方法和主 `classes.dex` 完全保持；60个恢复类中58个完整 IR 相同，仅 Store 的一个调用改变、ProviderReceipt 新增专用方法，原通用校验 IR 不变。664个非签名 ZIP payload 集合不变，只 `classes2.dex` 改变，Manifest/资源/权限逐字节保留。同证书 v3 和16KiB对齐通过。构建峰值595394560字节，memory max/OOM均0；存在8个 CPU throttle 周期，共922微秒。不是完整 AOSP clean build。

候选使用 Pocket4 实际 ART、固定52项 boot classpath、原 boot/APEX、PCL[] 和同 Main 严格守卫做隔离验证。66个新/修改目标类全部实际 Stored status Verified，没有缺失或其他未验证状态；compiler/oatdump均rc0、joined、未超时。末态限额与准入相同，内存峰164073472字节，memory events和CPU throttle均0。两个已观测 cache 根没有持久元数据变化；没有宣称捕获所有瞬时写入，也没有把隔离 classloader 上下文冒充 App 业务进程观察。

## 实际安装与下一轮边界

2026-11-05 19:09:20.276103–19:09:22.490884 UTC 完成唯一保留数据升级。实际单base APK2635213字节，SHA256 `00cb0b0a3e33a0bf79814a83c3c5900a3c10d9c41719d38e1e146a0ae134a85f`，包 com.android.calendar、user0、UID10061、version37、原 a40da80a 证书。一次 install、pending=false，无回滚。UID、CE/DE目录身份、完整权限行、首次安装时间、Provider身份、八表零行、task851及 b227/7e49 Main 边界均保持。这里只证明 data identity，没有全部私有 preferences 字节相等结论。

Core12 在此包冻结时尚未 stage 或执行，先由 Docs09 使用 UI，再回到实际首次LOCAL创建、取消无写、事件创建/编辑/关闭重开/详情/删除。Core12 保留既有业务预算，唯一功能修正是清理 URI 的 `%20` 编码；15项 host 控制器边界检查通过，不是 Android 业务通过。重复事件实例、提醒、实际宿主通知 Snooze 和恢复仍待运行验证；没有 whole-app production-ready 结论。

本增量依赖 public-extension10/SOURCE_MANIFEST.json（2a86e9ad4da4a73b77e813f679bff2f5501701f2c07517f98a72c76cf870d949）；完整输入 pins 在 source/SOURCE_PINS.json，其余源码按父版本复用。执行前计划、占位清理 pin 审阅和冻结时未执行字段均保留为历史，真实执行以对应原件 hash/selected/result/status 为准。未发布 APK、DEX、签名私钥、base64 stage、请求 envelope、私有 UI 图片、用户账号/事件内容或完整 proc/env。后续 Core12 结果独立追加，不改此冻结包。
