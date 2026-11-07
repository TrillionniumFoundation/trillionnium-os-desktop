# 独立公开交付候选：National 与 Uber

本次只做本地证据联接和公开网页研究，没有发起目标机任务、下载 APK、安装、UI、权限操作或清理。候选来源均为第三方公开分发；官网和 Play 证明产品身份，不证明厂商为分发站背书。两条路径均不使用已经失败的 IHG/APKMirror 通道。

## 两个候选

| 应用／当前实际身份 | 正常公开页面的新线索 | 尚未证明 |
|---|---|---|
| National `com.ehi.national.mobile`；6.15.0.9354 / code9354；UID10141；原4个APK | [Softonic 下载页](https://national-car-rental.en.softonic.com/android/download)列6.16.0.9403、独立XAPK控制、65.97MB和容器SHA。新[Play正文](https://play.google.com/store/apps/details?id=com.ehi.national.mobile)确有6.16系列说明。 | 真实literal文件URL、完整字节、ABI和全部split、code、每件正常签名；官方完整6.16.0.9403标签仍只继承原S22引用。 |
| Uber `com.ubercab`；4.651.10003 / code316108；UID10139；原10个APK | [Uptodown下载页](https://uber.en.uptodown.com/android/download)现列4.655.10001、arm64-v8a/armeabi-v7a、130.1MB XAPK；明示“All variants”可取单独XAPK。 | 精确手动URL、完整split/code/签名，以及该版本的独立官方版本关联；[Play](https://play.google.com/store/apps/details?id=com.ubercab)没有展示版本号。默认Download是商店安装器，不能采用。 |

National当前PM证书SHA256为 `bef72da965ea0b91d0d69aae9aae41bcc232fad8643adefcc85e5870db405cfa`；Uber为 `4003231ab42feb8d955e62fdfaa4fad59567054b9c6bbc3d950299ddfc268392`。将来的每个base/split都必须正常验签并与各自合法当前签名关联。当前身份来自已固定r3清单，本研究没有重新观察Main。

National分发页容器SHA标签为 `a901bc4949fe241750cd7ea3fb5df690d00b21e217b2212be813bbd51e5a36bb`；Uber为 `1250b932a610e3830fb78d9382ae1b5faecd347b5f19db0b76644c58498aa41e`。它们是网页声明，尚未用完整文件重算。XAPK不等同于完整单体APK，也不能直接交给旧单APK安装worker。必须先核清manifest、split依赖、arm64选择、相同versionCode及signer，再核原native多包安装能力；普通PM完整性校验保持有效。

## 固定的最小下一步

优先仅封 National：`exact-national-page-request.review-only.json`只允许一次普通UID1000 GET已列固定页面。默认urllib身份、正常TLS/解析器、最多2MiB正文、120秒内预算／180秒执行预算、256MiB内存。不跟随重定向，不请求任何binary、installer、API、后继链接或登录；403、挑战、超限、超时均失败终止，无重试或替代身份。新的key沿原任务前缀，输出目录日期反映2026-11-07。Uber仅保留研究，没有执行入口或第二份请求。

结果只报告完整HTML pin和有界literal控制。即使返回ok，也仅意味着页面观察完整；找不到普通链接必须保持UNRESOLVED。Uptodown的“All variants”如果是动态控制，本请求不会执行脚本、猜测API或用默认安装器代替。取得真实原文后才能独立准备正常文件交付请求。

10个原read/save/FD/HTTP定义逐字继承；唯一入口是National，新控制仅作未跟随控制提取及不把默认安装器当文件。4个本地实际控制通过，未运行网络。写入pin是本次写入bytes计算值，不声称另做过远端文件回读或目录断电持久性证明。

## 被保留的失败与未选线索

IHG job `1a1b3437276-fc05-818f` 实际failed1：首GET403、`Cf-Mitigated: challenge`，第二页未请求，0 APK/Main操作，FD恢复。完整原文和terminal在原目录，绝不改写。该lane终止，不能用浏览器、身份、端点/CDN、代理、TLS/DNS或旧nonce处理挑战。

TextNow/Malavida公开web请求也遇403，停止。Marriott原S44路径403不重试，另一个正常Uptodown页仍为已装10.79.0；Hertz另一页4.84.0更旧。TextFree Softonic仅导向Play，Aptoide版本页冲突且未取得独立URL；没有为第三个候选硬凑可交付结论。神州同版327既有候选不再下载。未找到某条厂商直链，不等于不存在任何合法公开同包签名包。

## 全46范围与证据限度

`SOURCE_GAPS_46.json`在原46行基础上保留每个包的已装版本、来源差距及12项实际升级，只更新两个新候选和IHG真实失败。46成员来自既有native/framework observation；本研究没有重新枚举，也不将后续helper安装等同于Launcher成员变化。29商业App中仍有17项未实际升级；2项此轮候选尚无APK资格。全部业务就绪为0，清理为0。

`RESEARCH.json`记录精确URL、web refs、原始输入pins、当前全部APK身份及停止路径。网页来源不是target HTTP回执，缓存/页面版本变化已经分开记录；不将分发站“latest”当官方最新版。原allowlist、guard、历史失败和授权边界都不变。
