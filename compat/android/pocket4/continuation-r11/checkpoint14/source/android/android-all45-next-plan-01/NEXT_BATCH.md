# Pocket4：45 App 下一批验收源码与计划

本件只整理下一批可审的范围，不执行 Android 命令、不扫 Main、不改引擎。45 行全部保留，整 App 资格仍为 **0 / 45**。公开核心流程通过也只产生该流程的局部资格。

## 输入与时间边界

权威 launcher 底册是 `2026-11-04T12:00:30.044481+00:00` 的快照，45 行中 39 行只记安装清单，SHA256 `05e74a719281abab717464978d85393dec8d0d528c1e7ccbd93691f156ce56e4`。其 182 个已安装包是历史观测值，下一请求不能把它当当前包数或 UID 清单。

补充使用同 Main epoch 的已发布 13 项局部流程核对记录：`commercial-flow-reconciliation-1524.json`，SHA256 `dd8641d92445ef3c7e5b43fa46eb9f1e064a8516722a3ef2b5b95beca7c09665`。本次从固定 Git commit 逐字取回并验 SHA；没有重新读完 13 份各自原始日志，也没有把核对记录当新执行。

原件出处：[45 行底册所在 CP12](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/9b8f4fb09e6c9d12f23f83ccd7a0071b699a7f54/compat/android/pocket4/continuation-r11/evidence/current-launcher-acceptance-matrix.json)；[13 项后续核对](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/9b8f4fb09e6c9d12f23f83ccd7a0071b699a7f54/compat/android/pocket4/continuation-r11/checkpoint-03/evidence/commercial-flow-reconciliation-1524.json)。两份输入的精确原字节在 `references/`，不回写旧状态。

按包用途为计划分组：29 个商业 App、11 个 `com.android` 系统 App、GMS 1、WebView shell 1、输入法 1、自有 fixture 2。用途分组不是新的设备观测，也不从 45 的分母中排除任何行。

## 紧接 Bilibili 的首批候选

R5 当前流程的实际回执优先于扩面。它的 helper 安装和不连接 UiAutomation 的 state 已通过；这不证明缓存假设或 UI 功能。新功能流程的原始失败/成功及清理必须独立消费。

本计划收口时，Root 已报告唯一新功能 job `1a1aadcfbb5-fc05-4837` 为 exit1、完整 durable、未超时；已给 coordinator/stage 精确 hash，safe8 原件 reader 已冻结，内层首因尚未读回。这里保留该失败，既不归因 Main/焦点/播放器，也不写成 R5 UI 未曾运行。

以下顺序是源码准备优先级，**不是批量启动清单**。所有页面和免登录路线都是待实际观察的候选，不能凭计划构造 selector。

| 顺序 | 固定目标 | 可完成的公开核心范围 | 下一份必需的控制 |
|---|---|---|---|
| 0 | `tv.danmaku.bili` | 先闭合当前 R5，继续视频画面、暂停/恢复、可见 seek、返回/重开、冷启和精确音频输出 | 保留已冻结包/UID/Main/window/恢复门；分别取得功能结果，不由详情页或播放状态推音频 |
| 1 | `com.amazon.mShop.android.shopping` | 从旧“查询与匹配建议”推进到真正商品结果、一项详情、返回 | 本次提交时复核公共输入；绑定商品结果卡与详情身份。登录或导航失败保留，不能把建议当结果 |
| 2 | `com.MobileTicket` | 固定公开路线/日期的车次结果与时刻详情、返回 | 本次请求固定站名/站码/日期，提交时读回，结果同路线同日；不选择旅客、购票或支付 |
| 3 | `com.ihg.apps.android` | 公开城市酒店列表、一项酒店详情、返回 | 城市/日期/酒店卡身份的单 App 选择器；不会员登录、选房确认或预订 |
| 4 | `com.bestbuy.android` | 固定公共商品查询、结果、一项详情、返回 | 本次新鲜树上的搜索/提交/商品 ID 合同；不购物车、收藏、结算或购买 |

先从这四个新目标中的一个完成精确包/版本/APK/签名/UID 只读绑定，再创建该 App 的单独 helper/adapter 源码和一次 fresh flow。登录、地区、位置、验证码或权限门实际出现时记录阻塞；不会自动绕过，也不会因此改用未经绑定的另一包。

## 现有 Bili 源码可以复用什么

可逐字复用的基础能力包括 R4 held namespace transport、Main/source 前后 guard、原 action flock、原 task 所有权、一次 nonce、完整树/window freshness、失败后的独立 after-state 和精确 cleanup。代码 pins 在 `coverage-plan.json`。复用代码不转移验收结论。

现有 R5 Java `PACKAGE = "tv.danmaku.bili"`、`TARGET_UID = 10117`，Python `qa_contract.PACKAGE/UID` 也固定 Bili。Java 还核实际 PackageManager UID、窗口包和每个节点包。**它不能直接用于其余 44 行。** 不会将常量换成 wildcard、任意请求包或宽 allowlist。

下一 App 最小源码增量是独立自有包及固化单目标合同：一个实际 target package/UID、一个 helper package/UID、一条真实 source/build/APK/signer 链。Java 与 Python 的目标、协议、构建后 manifest gate 必须一致。然后是新的 install/state 原件与实际 UID，最后才有 UI 准入。原 Bili helper 和所有旧源保持不动。

每个 App 仍缺以下运行时输入，计划不填猜测值：实际版本及 base/split APK hash、签名、UID/user；本次 Main epoch/held root；实际前台组件及 display；原有 task 集合；公开输入及页面的唯一 selector；一次流程 nonce 和准确动作预算。历史版本只是底册原字段。

## 具体适配合同

| 业务类型 | 必须新增的 App 内绑定 | 什么不能当成功 |
|---|---|---|
| 商品检索 | 本次 public query、提交前同输入、唯一商品卡、详情商品 ID/标题对应 | 建议、登录页、活动弹层、空列表、加载页 |
| 酒店/租车 | 公开城市/门店 ID、明确日期/时间、结果卡与详情身份 | 预订入口、价格 skeleton、会员首页或加载态 |
| 航班/列车 | 路线/站码或公开航班号、准确日期、结果航段/车次 | 日历画面、按钮 ACK、仅“加载中” |
| 房源/服务 | 公共地区/查询、唯一房源或服务 ID、详情和返回 | 推荐列表或账号门；不能联系经纪人/服务商 |
| 视频 | 实际公开视频身份、当前控件能力、时序/画面、独立真实输出归因 | 详情页、Surface、play-state、时间文字不能单独证明可见或可听播放 |
| 通信 | 另行批准的自有账号/收发端点及内容，严格只操作合成对象 | 欢迎页、账号页或用户聊天列表不能证明收发/通话；当前不发信/拨号 |
| 系统/输入/文件 | 自有隔离 fixture、精确 URI/provider/文件或合成记录、真实恢复及差分清理 | 有 launcher 图标或某个 fixture 通过不能覆盖商业 App |

所有 action 仍在自己的 fresh inspection 中重算唯一 selector；不能使用此前稳定检查留下的 node path 直接点。每个 submit 还须在**该次 action-bound inspection** 验证实际输入，不只在更早的读取中验证。

## 已知失败的处理顺序

Marriott、Hertz、Air China、Hyatt 的 native 启动问题，以及东航的独立 SIGILL/加载态，进入精确诊断队列；不能借 owned native probe 或候选完整构建通过写成商业修复完成。本计划不部署引擎，也不循环重启失败 App。

Meituan 旧主进程自退循环先解决启动/退出归因，再进入商家查询。Beike/JD 的账号路由阻塞和 StreetEasy 的 connection error 都保留，只有确切公开入口或必要的新诊断才创建下一次动作。SIGKILL 不能自动归为 LMKD；Gain 查询 EIO 不能自动归为 USB 断连。

WeChat 的已见首页画面和空语义树同时成立，不能把语义树空写成空白渲染。本轮不操作私人会话。TextNow/TextFree/WeChat 的完整核心通信业务在现有“不得发送/拨号”约束下保持未验，需要以后明确自有端点方案。

## 每行仍独立的整 App 门

`coverage-plan.json` 覆盖全部 45 个原包名，一行不漏，不新增或合并包。每行有原底册字段、后续已发布局部状态、候选核心流程、该 App 特有的新控制、尚未覆盖内容及明确 `plan_executable=false`。

公开核心流程后仍逐项检查：正常关闭/重开；有实际进程缺席证据的冷启；后台/恢复及进程重建；不破坏用户数据的持久化；授权范围内的网络失败/恢复与权限拒绝；精确进程归因的 crash/ANR/系统稳定；按 App 功能适用的音视频、外部交易或通信结果。未做的门保持 OPEN，不以“不适用”消掉真实核心需求。

没有原始商业树、截图、麦克风或混合音频进入这份计划。公开记录只保留输入公共值、scope、hash 和必要的状态/错误；登录信息、订单、联系人、位置和私人 feed 内容仍不导出。

## 本地验证与限制

`python3 -I make_plan.py` 仅读取已固定本地 JSON/源码和已有原件的 hash，生成声明式计划。没有网络、namespace、subprocess 或设备执行器。

本地验证证明：与权威底册的 45 个包集合严格相同；无重复/遗漏；原 39 个 pending 与 13 个补充局部记录计数未改；全部行非执行/非资格。它不证明任何候选页面存在、任何 App 可免登录使用或任何实际设备流程通过。
