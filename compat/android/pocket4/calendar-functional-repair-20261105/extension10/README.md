# Calendar10 首用路径修复、实际 ART 与升级证据

Calendar09 已修复菜单 VerifyError，但实际 Core10 在零日历状态下仍自动调用 AccountManager.addAccount，转到 Google 登录页。没有点击登录、输入认证内容或创建事件。原 launch unknown / failed 回执保留；独立只读证据绑定 task968 的 Calendar UID10061 与 task969 的 GMS UID10118、caller 和创建时间窗。随后正常关闭这两个确切自有任务，保留 task851，八张 Provider 表仍全为空。第一份清理脚本因读取了错误的 pending 键名而在任何 Android 命令前失败；新的 cleanup02 只修正为真实 ui_pending 字段。cleanup02 真实成功，原失败未覆盖。正常关闭期间有一条非 crash 进程退出记录，因此只声明 fresh crash/ANR 为零。

## 首用修复

Calendar10 保留原 QueryHandler 的计数、Activity 生命周期检查、Cursor 关闭及异常处理，只移除零日历分支的自动账号跳转。首次无日历时提示从 New event 显式创建本地日历；账号添加保留为用户明确选择的 Add account 菜单，并沿用原有 AccountManager 参数。安装不会创建日历、事件或账号。用户仍能选择本地日历和账号路径，取消编辑不会隐式种入测试数据。

真实构建以已安装09的精确输入为基准。445个原类、2327个方法仅 QueryHandler.onQueryComplete 改动；60个恢复类中59个完整类IR相同，仅 CalendarActions 增加首用提示与显式账号菜单。664个非签名 ZIP payload 集合保持，只有两个 DEX 改变，其余资源、Manifest 和权限逐字节一致。91项 Java 边界检查通过，同证书 v3 验证和16KiB对齐通过。构建是实际源码/DEX 增量组合，不冒充完整 AOSP clean build。

## 实际 ART 与安装

Root 以 Pocket4 已安装 ART、52项精确 boot classpath、原 boot/APEX、同 Main epoch，在独立2GiB/0swap/CPU20–21单元中执行候选验证。60个恢复类加6个修改原类，共66个精确目标全部为实际存储状态 Verified；共解析199个类头，没有缺失或其它未验证状态。compiler/oatdump均rc0、joined且无超时，末态资源限额与前置相同，内存峰145068032字节，max/oom/oom_kill及CPU throttle均0。PCL[]是隔离 App artifact 的验证上下文，不能据此声称已观察业务进程的实际 classloader。两个已知 cache 根没有持久元数据差异；不宣称捕获了所有瞬时写入。

2026-11-05 18:32:06.974744–18:32:09.210226 UTC 已执行唯一保留数据的升级。实际单base APK 2631117字节，SHA256 7872aa56b6aa35f4509a27a2c3c0ebb8743da7096136155e425f5b1e4499ae8e，仍为 com.android.calendar、user0、UID10061、version37、原a40da80a证书。UID、CE/DE目录身份、完整权限行、首次安装时间、Provider身份、八表零行、原task851及严格b227/7e49 Main边界均保持。此处只声明 data identity 保持，没有全部私有preferences字节相等结论。

## 资格与来源边界

本包冻结时 Core11 尚未执行。安装成功和ART通过不代表业务通过；首用LOCAL日历、取消无写、单事件创建/编辑/关闭重开/详情/删除由后续独立真实验收回执报告。重复事件实例显示、提醒交付、真实宿主通知 Snooze 和恢复等范围仍需实际验证；没有 whole-app production-ready 结论。源代码与控制器的未知操作不重放、不自动回滚或重装。

本增量依赖 public-extension09/SOURCE_MANIFEST.json（35682fcef2f218521da964ad35a53a1685af2412cf71acfb664eb80eaf4c1a69）。source/SOURCE_PINS.json列出完整构建输入，此目录仅覆盖10的变化，其余源按父版本精确复用。art10/EXECUTION_REVIEW.json中的executed=false是执行前计划的原记录，实际执行见同目录原始result/status/ack。execution11/PEER_REVIEW_DRAFT.json保留占位ART时的原审结，ART10_BINDING_PROOF.json证明之后唯一常量替换与真实66类前置校验。

没有发布APK、DEX、私钥、base64 stage、请求envelope、账号页面截图、认证内容、完整proc/env或用户日历内容。文件清单和精确SHA见SOURCE_MANIFEST.json；后续Core11结果将独立追加，不改本冻结包。
