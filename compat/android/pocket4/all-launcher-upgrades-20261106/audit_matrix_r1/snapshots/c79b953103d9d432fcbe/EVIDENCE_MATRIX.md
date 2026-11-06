# Pocket4 全部 Launcher App 证据矩阵

实际 user 0 MAIN/LAUNCHER 集合 **45 个 App / 45 个组件**。已尝试 45 个 App / 85 个 APK；整批联合审计通过 **42 个 App / 82 个 APK**，其余 3 个不能计为联合通过。

本轮已完成 **11 次升级**；另有 2 个 App 的当前 APK 与既有官方 release 资产摘要逐字节对应，1 个候选因签名冲突被阻止。**生产就绪 0，允许清理 0，已删除旧产物 0 B。**

这是一份已记录证据的本地合并快照，不会发起设备查询、安装、UI 操作、权限更改或清理。通过 APK 审计不代表核心业务、登录或访客、网络、存储、权限恢复、长时间运行、重启或故障恢复已经通过。

## 证据边界

- PM 枚举包含 205 个已装包；本次 Launcher 范围是实际解析得到的 45 个。完整 APK/数据身份另有 47 包固定范围（含 2 个 helper），不能把 205 行元数据说成 205 包完整验签。
- 版本名只取实际 base manifest。缺失或解析失败保留 UNKNOWN；历史版本名列于 JSON 独立字段。SDK 数值按实际工具原样保留，不修正看起来异常的 min/target 组合。
- 权限声明不等于已授予权限。当前只有贝壳有独立 user 0 PM/AppOps 原文派生快照，其余有效授权保持 UNKNOWN。缺失不能推断为 denied；AppOps 未标明 UID scope 的行不被扩大解释。
- 原 b05 失败原样保留；其独立纠正审计有单独真实终态。b13 的个体签名/manifest 观察不消除整批失败。
- 登录、核心业务、长时、应用重启、runtime 重启后每包回归与故障恢复尚未资格化。60 分钟、3 次应用重启、3 次网络恢复是本轮提出的门槛，不能写成历史已通过。
- 离线、系统、硬件 profile 按各自合同取证，不强制虚构 DNS/TLS、账号、通话或相机结果。reDroid 当前目标已退休，无当前测试结论可转移。
- Main 不执行 Bili Accept；历史 Accept 只限指定独立 cell。美团位置不得主动 grant。签名、完整性、任务归属、foreground、双 hash 与 UNKNOWN 约束全部保留。

## 当前名单、版本与 APK 结果

“原八项”标记原定八个 App。App 标签来自此前实际 Launcher 名称记录；包名与组件来自新的 PM resolver。† 表示仅失败批中的个体观察，不能计为联合审计通过。

| App（原八项） | 包名 | 实际版本名 / PM code | APK 数 | APK 联合结果 | 本轮升级 / 官方源状态 | Manifest 声明数 |
|---|---|---|---:|---|---|---:|
| Hyatt **原八项** | `com.Hyatt.hyt` | '26.9.0' / 26090096 | 3 | 通过 | 未完成新升级 | 26 |
| Railway 12306 | `com.MobileTicket` | '5.9.4.5' / 275 | 1 | 通过 | 未完成新升级 | 62 |
| Amazon Shopping | `com.amazon.mShop.android.shopping` | '32.18.0.100' / 1243240206 | 3 | 通过 | 未完成新升级 | 87 |
| Calendar | `com.android.calendar` | '17' / 37 | 1 | 通过 | 未完成新升级 | 15 |
| Camera | `com.android.camera2` | '2.0.002' / 20002000 | 1 | 通过 | 未完成新升级 | 23 |
| Contacts | `com.android.contacts` | '1.7.34' / 10734 | 1 | 通过 | 未完成新升级 | 30 |
| Clock | `com.android.deskclock` | '17' / 37 | 1 | 通过 | 未完成新升级 | 12 |
| Phone | `com.android.dialer` | '23.0' / 2900000 | 1 | 通过 | 未完成新升级 | 65 |
| Files | `com.android.documentsui` | '17' / 37 | 1 | 通过 | 未完成新升级 | 20 |
| Gallery | `com.android.gallery3d` | '1.1.40030' / 40030 | 1 | 通过 | 未完成新升级 | 23 |
| Messaging | `com.android.messaging` | '1.0.001' / 10001040 | 1 | 通过 | 未完成新升级 | 24 |
| Search | `com.android.quicksearchbox` | '17' / 37 | 1 | 通过 | 未完成新升级 | 8 |
| Settings | `com.android.settings` | '17' / 37 | 1 | 通过 | 未完成新升级 | 141 |
| ThreadNetworkDemoApp | `com.android.threadnetwork.demoapp` | '17' / 37 | 1 | 通过 | 未完成新升级 | 5 |
| Best Buy | `com.bestbuy.android` | '26.9.20' / 2012312321 | 3 | 通过 | 未完成新升级 | 39 |
| National | `com.ehi.national.mobile` | '6.15.0.9354' / 9354 | 4 | 通过 | 未完成新升级 | 31 |
| TextNow **原八项** | `com.enflick.android.TextNow` | '26.40.1.0' / 15733 | 3 | 通过 | 未完成新升级 | 84 |
| microG Settings | `com.google.android.gms` | '0.3.17.252432' / 252432034 | 1 | 通过 | 官方资产摘要同字节 | 92 |
| Hertz | `com.hertz.android.digital` | '5.6.0' / 1389 | 4 | 通过 | 未完成新升级 | 34 |
| Hilton Honors | `com.hilton.android.hhonors` | '2026.9.29' / 1004 | 4 | 通过 | 未完成新升级 | 31 |
| IHG | `com.ihg.apps.android` | '5.108.1' / 50023219 | 1 | 通过 | 未完成新升级 | 26 |
| JD.COM | `com.jingdong.app.mall` | '16.1.50' / 102918 | 1 | 通过 | 升级成功，业务待验 | 102 |
| 贝壳找房 **原八项** | `com.lianjia.beike` | '3.06.71' / 3067100 | 1 | 通过 | 升级成功，业务待验 | 69 |
| Marriott | `com.marriott.mrt` | '10.79.0' / 671 | 3 | 通过 | 未完成新升级 | 31 |
| TextFree | `com.pinger.textfree` | '13.28' / 260172 | 4 | 通过 | 未完成新升级 | 63 |
| Air China **原八项** | `com.rytong.airchina` | '7.53.0' / 75300 | 1 | 通过 | 升级成功，业务待验 | 69 |
| China Eastern Airlines (CEA) **原八项** | `com.rytong.ceair` | '9.5.16' / 239 | 1 | 通过 | 升级成功，业务待验 | 66 |
| 美团外卖 **原八项** | `com.sankuai.meituan.takeoutnew` | '8.83.2' / 800830002 | 1 | 通过 | 候选签名冲突 | 137 |
| DiDi | `com.sdu.didi.psnger` | '8.0.18' / 1208001805 | 1 | 通过 | 升级成功，业务待验 | 72 |
| 抖音 | `com.ss.android.ugc.aweme` | '41.0.0' / 410001 | 1 | 通过 | 升级成功，业务待验 | 288 |
| 神州租车 **原八项** | `com.szzc` | '9.6.1' / 327 | 1 | 通过 | 未完成新升级 | 45 |
| 淘宝 | `com.taobao.taobao` | '10.69.0' / 866 | 1 | 通过 | 升级成功，业务待验 | 101 |
| WeChat | `com.tencent.mm` | '8.0.80' / 3220 | 1 | 通过 | 升级成功，业务待验 | 118 |
| Uber | `com.ubercab` | '4.651.10003' / 316108 | 10 | 通过 | 未完成新升级 | 58 |
| United Airlines | `com.united.mobile.android` | '4.2.98' / 3617 | 4 | 通过 | 未完成新升级 | 44 |
| 拼多多 | `com.xunmeng.pinduoduo` | '8.30.0' / 83000 | 1 | 通过 | 升级成功，业务待验 | 21 |
| ExpandableTextViewLibrary | `com.zhubajie.client` | '9.5.11' / 369 | 1 | 通过 | 未完成新升级 | 58 |
| StreetEasy | `com.zillow.android.streeteasy` | '3.127.1' / 22850 | 4 | 通过 | 未完成新升级 | 28 |
| 携程旅行 | `ctrip.android.view` | '8.97.4' / 2133 | 1 | 通过 | 升级成功，业务待验 | 57 |
| ANA | `jp.co.ana.android.tabidachi` | '7.6.0' / 339 | 4 | 通过 | 未完成新升级 | 21 |
| Sidecar Verification | `local.pocket4.fixture` | UNKNOWN / 0 | 1 | 失败批，未资格化 | 未完成新升级 | 0 |
| WebView Browser Tester | `org.chromium.webview_shell` | '1.0' † / 1 | 1 | 失败批，未资格化 | 未完成新升级 | 12 |
| Owned Editor Contract | `org.droidloom.qa.editorcontract` | '1.0' † / 1 | 1 | 失败批，未资格化 | 未完成新升级 | 0 |
| Fcitx5 | `org.fcitx.fcitx5.android` | '0.1.3-0-g048f581c' / 114 | 1 | 通过 | 官方资产摘要同字节 | 5 |
| 哔哩哔哩 **原八项** | `tv.danmaku.bili` | '9.18.0' / 9180300 | 1 | 通过 | 升级成功，业务待验 | 82 |

Manifest 声明数包括 uses-permission 与 permission 等各类条目，也可能跨 split 重复；不是唯一权限数或有效授权数。JSON 保留每个 APK 的完整条目、原始名字、签名方案、证书 SHA256、APK 哈希及命令原文摘要。

## 11 次真实升级与保留旧 APK

| 包名 | versionCode 变化 | 保留旧 APK | 实际 job |
|---|---:|---:|---|
| `com.jingdong.app.mall` | 102810 → 102918 | 2 件 / 294389107 B | `1a1b120faf4-fc05-760d` |
| `com.lianjia.beike` | 3066010 → 3067100 | 1 件 / 227573032 B | `1a1b083d024-fc05-7115` |
| `com.rytong.airchina` | 75201 → 75300 | 1 件 / 206624542 B | `1a1b0943dea-fc05-7179` |
| `com.rytong.ceair` | 238 → 239 | 1 件 / 220958172 B | `1a1b092eb36-fc05-7170` |
| `com.sdu.didi.psnger` | 1208001404 → 1208001805 | 1 件 / 94582884 B | `1a1b10a9850-fc05-7547` |
| `com.ss.android.ugc.aweme` | 400801 → 410001 | 1 件 / 360503779 B | `1a1b125038f-fc05-7639` |
| `com.taobao.taobao` | 863 → 866 | 1 件 / 95402496 B | `1a1b108c6f9-fc05-7530` |
| `com.tencent.mm` | 3200 → 3220 | 1 件 / 285283432 B | `1a1b09ac6ca-fc05-71a4` |
| `com.xunmeng.pinduoduo` | 82600 → 83000 | 1 件 / 26325737 B | `1a1b1031e3b-fc05-74e4` |
| `ctrip.android.view` | 2100 → 2133 | 1 件 / 98783628 B | `1a1b11208ab-fc05-7582` |
| `tv.danmaku.bili` | 9161100 → 9180300 | 1 件 / 226519153 B | `1a1b117ada1-fc05-75ae` |

每次成功均验证原始 stdout、完整 durable 终态、唯一 native install 正常返回、当前 scope 的 UID/code/证书/完整 APK 字节对应及数据目录身份保留。京东保留原 base + arm64 split 两件，失败的 jd-01 仍单列。旧版本只保留，未清理。

## 权限与业务验收

贝壳：PM requested 63 行、install 权限 26 行均报告 granted=true；user 0 runtime 权限 15 行，其中 ACCESS_LOCAL_NETWORK=true，另外 14 行 false；AppOps 58 行按原文字面归属保存；roles UNKNOWN。七个前导空格的非规范 VIBRATE 名字保留，不修剪。不据 false 推断用户拒绝原因，不据快照声称权限拒绝恢复用例通过。

贝壳已真实启动和只读检查；两步探索的第一步关闭弹窗后独立后置观察成功，第二步在 dispatch 前因 INSPECTED_TREE_OR_WINDOW_CHANGED 被 helper 拒绝。整例 FAILED/UNKNOWN 原样保留；后续独立只读观察不等于新的点击授权，也不等于中文搜索成功。其他 App 的核心操作没有本轮完整资格化证据。

计划覆盖 136 个核心用例 / 12 个网络或离线 profile。以下每包计划仍为待执行验收合同，不能用计划文本当测试结果。

| 包名 | 登录 / 访客计划 | 核心操作计划 | 网络或本地 profile | 业务 / 长时 / 重启 / 恢复 |
|---|---|---|---|---|
| `com.Hyatt.hyt` | authorized_login_required_for_core | 手动城市/日期酒店搜索；房型、价格和取消条件读回；World of Hyatt账号会话 | `vendor_https` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.MobileTicket` | try_existing_authorized_guest_or_public_browsing_then_login_if_app_requires | 车次、座席与票价查询；列车时刻与经停信息；正常登录/乘车资料边界 | `vendor_https` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.amazon.mShop.android.shopping` | try_existing_authorized_guest_or_public_browsing_then_login_if_app_requires | 中文/英文商品搜索和筛选；商品详情与规格读回；自有测试购物车或收藏状态 | `vendor_https` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.android.calendar` | no_service_login_for_planned_local_core | 本地测试事件创建/修改；日/周/月切换与提醒；进程重建后事件持久化 | `offline_local` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.android.camera2` | no_service_login_for_planned_local_core | 真实相机取景和拍照；短视频和音频录制；相机占用/权限与生命周期 | `offline_local` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.android.contacts` | no_service_login_for_planned_local_core | 本地中文测试联系人；受控vCard导入/导出；重启后联系人和权限拒绝行为 | `offline_local` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.android.deskclock` | no_service_login_for_planned_local_core | 受控定时器与闹钟；秒表计时和前后台；重开/重启后闹钟状态 | `offline_local` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.android.dialer` | no_service_login_for_planned_local_core | 拨号输入和电话角色；受控语音呼出/呼入；自有测试通话记录 | `cellular_telephony` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.android.documentsui` | no_service_login_for_planned_local_core | 自有测试文件创建/复制/重命名；SAF选择/取消与URI权限；只读/不可用文档provider | `offline_local` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.android.gallery3d` | no_service_login_for_planned_local_core | 测试照片/视频枚举与解码；实际支持的可逆图片编辑；受控接收组件的URI分享 | `offline_local` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.android.messaging` | no_service_login_for_planned_local_core | 合成短信草稿与输入；受控SMS收发；实际启用MMS附件收发 | `cellular_telephony` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.android.quicksearchbox` | no_service_login_for_planned_local_core | 中文/英文查询输入与编辑；实际本地provider或Web搜索结果；建议、取消与返回 | `local_search_with_delegation` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.android.settings` | no_service_login_for_planned_local_core | 系统与应用详情读回；权限页面与现有状态；网络/存储状态页面 | `system_settings` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.android.threadnetwork.demoapp` | no_service_login_for_planned_local_core | 真实Thread服务/设备识别；自有Thread网络入网；受控IPv6连通与故障恢复 | `thread_ipv6_lan` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.bestbuy.android` | try_existing_authorized_guest_or_public_browsing_then_login_if_app_requires | 中文/英文商品搜索和筛选；商品详情与规格读回；自有测试购物车或收藏状态 | `vendor_https` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.ehi.national.mobile` | try_existing_authorized_guest_or_public_browsing_then_login_if_app_requires | 手动网点及取还车查询；车型报价与条款；返回修改与持久化 | `vendor_https` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.enflick.android.TextNow` | authorized_login_required_for_core | 合法账号登录和会话恢复；受控文本双向收发；受控通话连接、音频与挂断 | `vendor_rtc` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.google.android.gms` | no_service_login_for_planned_local_core | 实际服务配置与自检读回；受控客户端调用真实API；已启用推送/账号服务验证 | `microg_service` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.hertz.android.digital` | try_existing_authorized_guest_or_public_browsing_then_login_if_app_requires | 手动网点及取还车查询；车型报价与条款；返回修改与持久化 | `vendor_https` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.hilton.android.hhonors` | try_existing_authorized_guest_or_public_browsing_then_login_if_app_requires | 手动城市/日期酒店搜索；房型、价格和取消条件读回；Hilton Honors账号会话 | `vendor_https` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.ihg.apps.android` | try_existing_authorized_guest_or_public_browsing_then_login_if_app_requires | 手动城市/日期酒店搜索；房型、价格和取消条件读回；IHG One Rewards账号会话 | `vendor_https` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.jingdong.app.mall` | try_existing_authorized_guest_or_public_browsing_then_login_if_app_requires | 中文/英文商品搜索和筛选；商品详情与规格读回；自有测试购物车或收藏状态 | `vendor_https` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.lianjia.beike` | try_existing_authorized_guest_or_public_browsing_then_login_if_app_requires | 中文房源查询；筛选与房源详情；新版本查询持久化 | `vendor_https` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.marriott.mrt` | try_existing_authorized_guest_or_public_browsing_then_login_if_app_requires | 手动城市/日期酒店搜索；房型、价格和取消条件读回；Marriott Bonvoy账号会话 | `vendor_https` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.pinger.textfree` | authorized_login_required_for_core | 合法账号登录和会话恢复；受控文本双向收发；受控通话连接、音频与挂断 | `vendor_rtc` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.rytong.airchina` | try_existing_authorized_guest_or_public_browsing_then_login_if_app_requires | 航班和票价查询；航班动态查询；查询状态与导航恢复 | `vendor_https` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.rytong.ceair` | try_existing_authorized_guest_or_public_browsing_then_login_if_app_requires | 航班和票价查询；航班动态查询；查询状态与导航恢复 | `vendor_https` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.sankuai.meituan.takeoutnew` | try_existing_authorized_guest_or_public_browsing_then_login_if_app_requires | 手动城市/配送地址；商家与菜单查询；可逆测试购物车 | `vendor_https` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.sdu.didi.psnger` | authorized_login_required_for_core | 手动起终点与路线；车型、预估费用和等待时间；路线编辑和丢网恢复 | `vendor_https` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.ss.android.ugc.aweme` | try_existing_authorized_guest_or_public_browsing_then_login_if_app_requires | 中文公开视频搜索；真实音视频播放；网络中断与播放器恢复 | `public_media` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.szzc` | try_existing_authorized_guest_or_public_browsing_then_login_if_app_requires | 手动网点及取还车查询；车型报价与条款；返回修改与持久化 | `vendor_https` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.taobao.taobao` | try_existing_authorized_guest_or_public_browsing_then_login_if_app_requires | 中文/英文商品搜索和筛选；商品详情与规格读回；自有测试购物车或收藏状态 | `vendor_https` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.tencent.mm` | authorized_login_required_for_core | 合法账号登录和会话恢复；受控文本双向收发；受控通话连接、音频与挂断；受控附件/语音或视频会话 | `vendor_rtc` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.ubercab` | authorized_login_required_for_core | 手动起终点与路线；车型、预估费用和等待时间；路线编辑和丢网恢复 | `vendor_https` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.united.mobile.android` | try_existing_authorized_guest_or_public_browsing_then_login_if_app_requires | 航班和票价查询；航班动态查询；查询状态与导航恢复 | `vendor_https` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.xunmeng.pinduoduo` | try_existing_authorized_guest_or_public_browsing_then_login_if_app_requires | 中文/英文商品搜索和筛选；商品详情与规格读回；自有测试购物车或收藏状态 | `vendor_https` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.zhubajie.client` | try_existing_authorized_guest_or_public_browsing_then_login_if_app_requires | 实际应用身份与启动品牌核对；中文服务搜索；服务商/作品与条款详情 | `vendor_https` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `com.zillow.android.streeteasy` | try_existing_authorized_guest_or_public_browsing_then_login_if_app_requires | 手动区域/地址房源搜索；地图与房源详情联动；可逆保存搜索 | `vendor_https` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `ctrip.android.view` | try_existing_authorized_guest_or_public_browsing_then_login_if_app_requires | 酒店查询；航班查询；火车票查询 | `vendor_https` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `jp.co.ana.android.tabidachi` | try_existing_authorized_guest_or_public_browsing_then_login_if_app_requires | 航班和票价查询；航班动态查询；查询状态与导航恢复 | `vendor_https` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `local.pocket4.fixture` | no_service_login_for_planned_local_core | 解析真实ProbeActivity探针协议；执行源码明确的探针动作；探针拒绝路径与重启 | `local_qa_contract` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `org.chromium.webview_shell` | no_service_login_for_planned_local_core | 实际WebView实现与renderer；受控HTTPS页面与中文输入；网页存储和文件选择 | `webview_https` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `org.droidloom.qa.editorcontract` | no_service_login_for_planned_local_core | 当前编辑器测试契约；真实中文输入、选择与删除；焦点、前后台和恢复 | `local_qa_contract` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `org.fcitx.fcitx5.android` | no_service_login_for_planned_local_core | 当前IME与中文引擎配置；拼音/候选和字符提交；跨App焦点与字典持久化 | `local_ime` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |
| `tv.danmaku.bili` | try_existing_authorized_guest_or_public_browsing_then_login_if_app_requires | 中文公开视频搜索；真实音视频播放；网络中断与播放器恢复 | `public_media` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |

每包 JSON 还列出适用的账号、受控对端、硬件、存储、权限与失败路径要求；未提供的输入保持 UNKNOWN，不替换为 N/A。

## 批次状态及失败归因

| 批次 | 原始状态 / 当前证据关系 | job |
|---:|---|---|
| 1 | `FROZEN_ORIGINAL_JOINT_GATE_PASSED` | `1a1b147aa03-fc05-777c` |
| 2 | `FROZEN_ORIGINAL_JOINT_GATE_PASSED` | `1a1b14f8ce1-fc05-77ac` |
| 3 | `FROZEN_ORIGINAL_JOINT_GATE_PASSED` | `1a1b15d8829-fc05-780a` |
| 4 | `FROZEN_ORIGINAL_JOINT_GATE_PASSED` | `1a1b1684dc2-fc05-7871` |
| 5 | `INDEPENDENT_CORRECTION_JOINT_GATE_PASSED_ORIGINAL_FAILED_PRESERVED` | `1a1b289b789-fc05-7e7e` |
| 6 | `FROZEN_LINKED_JOINT_GATE_PASSED` | `1a1b29d3379-fc05-7eef` |
| 7 | `FROZEN_LINKED_JOINT_GATE_PASSED` | `1a1b29f8bb9-fc05-7efe` |
| 8 | `FROZEN_LINKED_JOINT_GATE_PASSED` | `1a1b2a04bff-fc05-7f03` |
| 9 | `FROZEN_LINKED_JOINT_GATE_PASSED` | `1a1b2a29563-fc05-7f13` |
| 10 | `FROZEN_LINKED_JOINT_GATE_PASSED` | `1a1b2a4d290-fc05-7f1c` |
| 11 | `FROZEN_LINKED_JOINT_GATE_PASSED` | `1a1b2a76798-fc05-7f29` |
| 12 | `FROZEN_LINKED_JOINT_GATE_PASSED` | `1a1b2a90ea8-fc05-7f31` |
| 13 | `FAILED_JOINT_GATE_RAW_OBSERVATIONS_ONLY` | `1a1b2ab7980-fc05-7f3a` |

当前失败批的具体 package parse_errors 在 JSON 的 observed_failure_paths 与每件 APK 中保留。fixture 的 AAPT_PACKAGE_VERSION_REQUIRED 不是签名失败；版本属性的合法默认语义仍需独立源证据和新修订验证，不能在本矩阵中猜补。

## 可复现来源

本生成器只读取显式固定的项目证据。成功 APK 批重用冻结原 gate 与 linked gate 的原检查，未调用 claim；已读取的每份文件在输出前重新散列。INPUTS.json 记录完整输入路径、字节数与 SHA256。

[实际 PM / resolver 结果](../../../successor_audit_requests/current_services_r4/actual/worker.stdout.original.json)（79176 B；SHA256 `185c6b0900aab78228e44788ea28b10d71c39cfeee8846fcb8c99c13a9f123fc`）

[当前 47 包字节 / UID / 数据身份](../../../successor_audit_requests/explicit47_scope_r2/actual-readback/app-scope.private.json)（58854 B；SHA256 `44f9ce783000a672c270e98afdaeb74bd79654508bfacae6793316ff4252e52f`）

[冻结 linked audit gate](../../../successor_audit_requests/revisions/linked-official-continuation-r2/linked_audit_gate.py)（34438 B；SHA256 `0befe9f69aa46608a6cec8505c1fed41cd8fca1f9045693c43a83dbb4fa00d8e`）

[45 App / 136 用例计划](../../../app_test_catalog.json)（624217 B；SHA256 `d16a51f06be2b4ba2b5a61991dd649d481d1fdf53ff1ccf570ea23367611cb19`）

运行：在项目根目录执行 `python3 -B audit_matrix_r1/build_matrix.py --write-snapshot`。输出到按输入摘要命名的新目录；已有相同快照只核对原字节，不覆盖。运行成功只表示本地证据矩阵生成成功。
