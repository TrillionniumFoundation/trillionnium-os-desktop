#!/usr/bin/env python3
"""Offline, declarative coverage planning. This module has no device executor."""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MATRIX_SHA = '05e74a719281abab717464978d85393dec8d0d528c1e7ccbd93691f156ce56e4'
RECON_SHA = 'dd8641d92445ef3c7e5b43fa46eb9f1e064a8516722a3ef2b5b95beca7c09665'

# These are proposed checks, not assertions that a page or unauthenticated route exists.
# Package and historical version come only from the exact published 45-row matrix.
SPECS = [
 ('com.Hyatt.hyt','commercial','native_failure','先核一次新启动的 JNI 初始化结果；能留在公开首页后再提城市酒店检索。','绑定实际加载库/进程出生与 JNI 结果；不得把 JNI_OnLoad -500 当作正常返回。','已知 JNI 失败未有修复 A/B；酒店结果和详情均未验。'),
 ('com.MobileTicket','commercial','next_public_core','候选：固定公开出发站、到达站、日期查询车次，读到车次列表及一项公开时刻详情，再返回。','站点必须绑定站码/可见名称，日期必须来自本次请求并在提交前读回；结果必须同路线同日。','尚无当前业务证据；购票、旅客、支付和账号流程不在本轮。'),
 ('com.amazon.mShop.android.shopping','commercial','next_public_core','延续既有公开查询：从匹配建议推进到实际商品结果，打开一个明确商品详情并返回。','新鲜输入值、提交按钮、唯一商品卡和详情商品身份逐步绑定；建议列表不能冒充商品结果。','旧查询/建议/返回局部已见，商品结果/详情未完成；不加购物车或购买。'),
 ('com.android.calendar','platform_ui','owned_platform_fixture','在隔离的自有测试日历中核月份导航及一项自有事件的显示和恢复。','必须先有只含自有合成事件的 fixture 和精确数据清理协议；不把用户日程读入公开证据。','目前仅 launcher 清单；事件增删/提醒/同步需单独权限和数据方案。'),
 ('com.android.camera2','platform_ui','owned_platform_fixture','在独立自有图像源上核相机预览与一张自有照片，精确清理输出。','输入设备/流/帧归属必须固定；UVC 可选 Gain 的 EIO 不能直接当 USB 断连原因。','不启真实私人相机或麦克风；源设备、权限现状和输出尚未绑定。'),
 ('com.android.contacts','platform_ui','owned_platform_fixture','在仅有自有合成联系人的隔离数据域核查找、详情、编辑与恢复。','精确自有 contact/provider row 身份和差分清理；不得以用户联系人作为 fixture。','当前不能授权通信或授予联系人权限；Main 真实数据保持。'),
 ('com.android.deskclock','platform_ui','readonly_system_scope','候选：打开时钟页和秒表页，核公开时间显示及返回；启动计时另行受限。','不得创建/删除已有闹钟；如做秒表仅清理本次自有状态，并核真实时间推进。','闹铃声音、后台唤醒、重启恢复都未验，不能由时钟画面推出。'),
 ('com.android.dialer','platform_ui','owned_platform_fixture','候选：仅拨号盘和空输入返回；完整通话只在独立自有电话端点 fixture。','无拨号动作；不能使用真实联系人/通话记录作为测试对象。','通话建立、音频路由、挂断和紧急呼叫不在当前授权范围。'),
 ('com.android.documentsui','platform_ui','owned_platform_fixture','候选：只浏览独立自有目录，打开一个自有文本/图片并返回。','固定 document URI、provider、文件 inode/hash 和只读 grant 范围；拒绝用户目录。','文件选择及写回需自有 fixture；不能从 launcher 通过推文件业务。'),
 ('com.android.gallery3d','platform_ui','owned_platform_fixture','候选：浏览一张自有测试图片、缩放/返回。','图片 source hash、内容 URI 和页面归属绑定；不遍历私人相册。','媒体库隔离、权限现状、视频解码及持久化均待准备。'),
 ('com.android.messaging','platform_ui','owned_platform_fixture','在自有隔离数据域核空页面与自有合成会话显示；无发送。','收件人/发送按钮必须禁止；如需草稿只允许合成号码且有精确回收协议。','真实 SMS/MMS 的发送接收和通知未授权/未验。'),
 ('com.android.quicksearchbox','platform_ui','readonly_system_scope','候选：固定公开查询并核可见结果；任何跨包结果先停在边界。','查询只允许本次固定公共字符串；跨浏览器/搜索 provider 不能借本包 scope 执行。','实际 provider 和跨 App 合同尚未知。'),
 ('com.android.settings','platform_ui','readonly_system_scope','候选：只读关于设备页并返回。','固定只读页面；禁止开关、网络、权限、账号、开发者选项和系统设置写入。','属于系统诊断作用域，不能替代商业 App 业务验收。'),
 ('com.android.threadnetwork.demoapp','platform_ui','owned_platform_fixture','先明确其现有构建和自有 Thread 测试网络，再提出离线演示。','不得加入/创建/改变当前网络；固定测试网络身份与终态回收。','未知凭据、硬件和设备拓扑；仅安装清单不能产生核心流程资格。'),
 ('com.bestbuy.android','commercial','next_public_core','候选：固定公开商品查询，核结果、一个商品详情、返回。','搜索框/提交/商品唯一标识来自本次树；禁购物车、收藏、结算和购买。','尚无业务证据；若登录、地区或位置门阻断则保留原结果，不绕过。'),
 ('com.ehi.national.mobile','commercial','public_core_backlog','候选：公开租车地点检索、固定时段可用车型、车型详情与返回。','门店代码、完整起止日期时间与车型卡身份逐项固定；提交前检查实际输入。','无预订、司机资料或支付；时区/日期和地点必须在本次请求中明确。'),
 ('com.enflick.android.TextNow','commercial','communications_privacy_bound','先核公开欢迎/帮助页及返回；核心收发/通话只在单独批准的自有账号和端点。','不发送消息、不拨号、不读用户会话；登录墙和账号选择不能自动越过。','实际消息/电话核心功能在当前约束下不能完成资格。'),
 ('com.google.android.gms','service','service_dependency','先界定清单中实际 launcher 组件；以自有依赖 probe 检验明确 API，勿当独立商业业务。','每个服务 API 的 caller UID、scope、实际返回与错误单独绑定；不登录/改账号/授予权限。','GMS 名称不是可直接执行的一项核心业务；依赖资格仍按调用者证据。'),
 ('com.hertz.android.digital','commercial','native_failure','先复现或排除一次精确启动 SIGSEGV；存活后才提公开门店/车型查询。','包/实际库/进程出生/信号精确归因；启动确认不能当业务成功。','旧已确认 SIGSEGV，原因/修复未证；不循环重启掩盖失败。'),
 ('com.hilton.android.hhonors','commercial','public_core_backlog','候选：公开城市检索、酒店列表、一个酒店详情和返回。','城市/酒店身份与日期绑定；价格仅记录实际观测，不选择房间/确认预订。','首页及免登录路线尚未实测，会员/预订业务未覆盖。'),
 ('com.ihg.apps.android','commercial','next_public_core','候选：公开城市检索、酒店列表、一个酒店详情和返回。','精确城市、日期、酒店卡及详情身份；禁会员登录、入住人、预订与支付。','尚无业务证据；登录/地区/定位要求必须作为阻塞记录。'),
 ('com.jingdong.app.mall','commercial','public_path_gated','保持旧建议/登录墙证据；新独立观察仅确认是否存在公开商品详情入口。','登录视图必须分类为门控，不提交手机号；受保护截图不是渲染失败。','旧提交后到手机号登录，商品结果/详情未验；不绕过账号限制。'),
 ('com.lianjia.beike','commercial','public_path_gated','保留旧建议结果和空白登录路由；只在新明确公共入口下提一个公开房源详情。','公共 query、房源卡/详情 ID 与路由目标绑定；遇登录页/空页立即留原失败。','列表/详情未验；不联系经纪人、不发消息、不拨号。'),
 ('com.marriott.mrt','commercial','native_failure','先对实际平台候选完成隔离资格；本 App 再作一次精确启动和公开酒店检索。','真实 SIGSEGV 与 proc-fd 观察分开；不能将候选 metadata/owned probe 绿作为商用修复 A/B。','原 native SIG11 与路径错配观察保留；Main 新引擎未部署/本计划不部署。'),
 ('com.pinger.textfree','commercial','communications_privacy_bound','先核公开欢迎/帮助页；完整消息/通话必须自有账号和受控接收端。','禁止发信、拨号、读已有私人会话；不自动注册/登录。','当前公开页不足以完成通信核心资格。'),
 ('com.rytong.airchina','commercial','native_failure','先取一次新启动的精确进程退出/存活证据，再提公开航班查询。','SIGKILL 发送者/内存因果必须有直接证据；不把 signal9 自动判 LMKD。','旧启动 SIGKILL、未完成 task receipt，原因未定。'),
 ('com.rytong.ceair','commercial','native_failure','分别保留旧 SIGILL 与后续首页/日历/加载记录；新单次公开航班查询核真实结果或明确错误。','结果必须匹配本次路线日期；同步信号修复的 owned SMC 资格不能替代东航商业回归。','原 SIGILL 未被后来的加载页撤销；结果加载失败原因仍未证。'),
 ('com.sankuai.meituan.takeoutnew','commercial','native_failure','先关闭启动自退循环的诊断缺口；存活后仅做手动公共城市/商家查询与详情。','先区分主进程 exit0/self-loop 和 crash；不自动重启，不访问订单或真实地址。','旧未尝试商家检索；不下单、改地址或授权定位。'),
 ('com.sdu.didi.psnger','commercial','public_core_backlog','候选：公开服务介绍或手工城市入口；只有明确免账号路线才能读车型说明。','不使用当前私人定位/住址，不填写实际行程、不呼叫司机。','叫车核心功能涉及外部效果，当前不授权完整验收。'),
 ('com.ss.android.ugc.aweme','commercial','media_backlog','延续旧公开 feed/详情/返回证据；下一步固定公共搜索及一项公开视频的控制。','搜索/视频身份、播放状态与真实输出链分别归因；禁止互动、关注、点赞、分享。','旧未验搜索、音频/播放控制；不能复用 Bili selector 或音频资格。'),
 ('com.szzc','commercial','public_core_backlog','先单次新启动/只读观察，再按实际公共门店页提出车型查询。','现有底册仅 pending；历史口述崩溃不能在缺精确原件时改写成已证原因。','需实际包/进程/页面证据；不预订、登记驾照或支付。'),
 ('com.taobao.taobao','commercial','public_core_backlog','候选：固定公开商品查询、结果和一个商品详情，再返回。','登录/验证码停在门前；商品 ID 与本次 query、详情绑定。','不购物车、收藏、客服、订单或购买；免登录路线待实测。'),
 ('com.tencent.mm','commercial','communications_privacy_bound','保留可见首页但语义树空的事实；只用明确安全页面和专门观察方案准备后续。','空语义树不等于空白画面；不得从私人聊天页做泛截图坐标动作。','互动/消息/通话未验；受控账号端点与非私人 fixture 是核心资格前置。'),
 ('com.ubercab','commercial','public_core_backlog','候选：公开服务/城市说明；不进入有实际派单效果的流程。','禁止真实起终点、报价确认、叫车或定位权限改变。','核心叫车功能需另外批准的受控外部效果；本轮仅公开页候选。'),
 ('com.united.mobile.android','commercial','public_core_backlog','候选：固定公开航班号/日期的航班状态及航段详情，再返回。','航班号、日期、机场与结果绑定；不使用 PNR、旅客姓名、值机或购买。','实际公共入口/结果页尚未观察。'),
 ('com.xunmeng.pinduoduo','commercial','public_core_backlog','候选：公开商品搜索、结果、明确商品详情及返回。','登录和活动弹层不能泛化点击；固定 query 和商品 ID，禁止签到/拼团/分享。','免登录入口与商品页待证；不加购物车/订单/支付。'),
 ('com.zhubajie.client','commercial','public_core_backlog','候选：公开服务类别/关键词检索及一个服务详情。','服务卡与详情身份绑定；禁止发需求、联系商家或发送消息。','账号门与公共浏览入口待证，交易业务未覆盖。'),
 ('com.zillow.android.streeteasy','commercial','public_path_gated','保留旧 connection-error；在新观测允许时只进行一次公开区域/房源查询。','错误必须按实际网络/页面证据分类；不自动反复重试、不换代理/安全配置。','旧未到房源结果，网络因果未证；不联系中介、不预约。'),
 ('ctrip.android.view','commercial','public_core_backlog','候选：公开城市酒店检索、列表与一家酒店详情。','城市/日期/酒店身份固定，拒绝自动读取行程、订单、入住人。','酒店/航班/火车为不同业务，首个公共酒店 scope 不能覆盖全部。'),
 ('jp.co.ana.android.tabidachi','commercial','public_core_backlog','候选：固定公开航班状态/时刻查询及航段详情。','航班日期/机场/航段绑定；禁止会员登录、订单、值机或购票。','实际免登录入口及结果尚未观察。'),
 ('local.pocket4.fixture','owned_fixture','owned_source_first','先恢复安装包的自有 source/build/signature 合同，定义该 fixture 的真实用途。','未知 fixture 不能借包名推断无害/可运行；先 source 到 APK 精确映射。','versionCode0/launcher 存在不产生任何商业 App 覆盖。'),
 ('org.chromium.webview_shell','webview_test_shell','owned_source_first','先绑定其实际 APK/源码；仅加载自有可审的 HTTPS/离线页面 fixture。','固定页面和资源哈希、导航 origin、网络错误分类；不绕清晰文本或证书安全。','WebView shell 资格不能自动覆盖商业 App 内嵌 WebView。'),
 ('org.droidloom.qa.editorcontract','owned_fixture','owned_source_first','先绑定实际自有源码/APK后核合成输入字段的编辑合同。','输入仅合成数据；自身 fixture、输入法与目标字段身份分开。','它不是 Bili 新 helper，也不能把两者安装/源码/签名混用。'),
 ('org.fcitx.fcitx5.android','input_method','owned_platform_fixture','只在独立自有编辑器中核明确 Unicode 输入/候选提交与返回。','不得切换现用输入法、改设置或输入私人字段；先约定隔离测试域和现有配置。','键盘显示不证明编辑/持久化；跨 App 输入需要独立端到端绑定。'),
 ('tv.danmaku.bili','commercial','active_bili','优先收 R5 新流程；继续真实画面推进、暂停/恢复、可见 seek、返回/重开、冷启及本 App 输出归因。','保持现有包/UID10117、helperUID10170、完整树/window freshness、Main/restore/task cleanup；每项能力需实际控件和新请求。','原 search/结果/详情仅 scoped；R5 安装/state 通过不等于 cache 或 UI 通过，音频/重开等仍 OPEN。'),
]

def sha(b):
    return hashlib.sha256(b).hexdigest()

def read_exact(rel, expected):
    p = HERE / rel
    b = p.read_bytes()
    assert sha(b) == expected
    return json.loads(b)

def file_pin(rel):
    b = (ROOT / rel).read_bytes()
    return {'local_path': str(ROOT / rel), 'bytes': len(b), 'sha256': sha(b)}

def main():
    matrix = read_exact('references/current-launcher-acceptance-matrix.json', MATRIX_SHA)
    recon = read_exact('references/commercial-flow-reconciliation-1524.json', RECON_SHA)
    by_package = {x[0]: x for x in SPECS}
    assert len(by_package) == len(SPECS) == 45
    assert set(by_package) == {x['package'] for x in matrix['apps']}
    later = {x['package']: x for x in recon['reported_scoped_flows']}
    rows = []
    for index, original in enumerate(matrix['apps'], 1):
        package, kind, lane, flow, control, remaining = by_package[original['package']]
        evidence = later.get(package)
        rows.append({
            'index': index, 'package': package, 'label_from_inventory': original['app'],
            'kind_for_planning_only': kind, 'lane': lane,
            'historical_inventory_row': original,
            'later_published_scope': ({k: evidence[k] for k in ['status','evidence_url','production_ready']}
                                      if evidence else None),
            'new_runtime_uid': 10117 if package == 'tv.danmaku.bili' else None,
            'new_runtime_artifact_binding': None,
            'public_core_candidate': flow, 'specific_control_to_add': control,
            'remaining_or_excluded': remaining,
            'selector_source': 'fresh actual single-app observation required; no guessed nodes/coordinates',
            'helper_admission': ('existing frozen R5 Bili source/build/install chain; functional attempt reported failed; phase receipts not yet consumed'
                                if package == 'tv.danmaku.bili' else
                                'new independently pinned single-app helper/adapter required; existing Bili helper rejects this package'),
            'plan_executable': False, 'new_device_observation': False,
            'scoped_pass_created_by_this_plan': False, 'whole_app_production_ready': False,
        })
    reused = [
        'owned-bili-qa-r5-cache-build02/source/src/org/droidloom/qa/bili/r5/ActionRunner.java',
        'owned-bili-qa-r5-cache-build02/source/qa_contract.py',
        'owned-bili-qa-r5-cache-build02/source/qa_adapter.py',
        'android-qa-install-state-02/r4/bound_android_transport.py',
        'android-qa-install-state-01/review-inputs/held_runtime_r5.py',
        'android-qa-install-state-01/review-inputs/recorder.py',
        'android-bili-r5-buffer-viewport-01/SOURCE_PINS.json',
    ]
    evidence_paths = [
        'root-recovery-20261104-02/evidence/qa-r5-install-state03-read01/worker.json',
        'root-recovery-20261104-02/evidence/qa-r4-buffer-viewport01/navigation.json',
        'root-recovery-20261104-02/evidence/qa-r3-stable-search01/navigation.json',
        'root-recovery-20261104-02/evidence/qa-r3-results-observe01/navigation.json',
        'root-recovery-20261104-02/evidence/qa-r3-video-transition01/navigation.json',
    ]
    plan = {
        'schema': 'pocket4-all45-next-batch-source-plan-v1',
        'prepared_utc_date': '2026-11-05', 'planning_only': True,
        'device_commands': 0, 'UI_actions': 0, 'Main_runtime_changes': 0,
        'all_apps_production_ready': False, 'whole_app_qualified_count': 0,
        'inventory_sha256': MATRIX_SHA, 'inventory_observed_utc': matrix['observed_at_utc'],
        'inventory_framework_epoch_sha256': matrix['framework_epoch_sha256'],
        'historical_launcher_count': 45, 'historical_pending_count': 39,
        'historical_installed_package_count': 182,
        'current_installed_package_count': None,
        'later_reconciliation_sha256': RECON_SHA,
        'later_reconciliation_observed_utc': recon['recorded_utc'],
        'later_reconciliation_scope': recon['scope'],
        'later_reported_scoped_flow_count': len(later),
        'reconciliation_was_retrieved_by_immutable_git_file_and_hash': True,
        'individual_thirteen_raw_evidence_files_reread_in_this_plan': False,
        'matrix_and_original_failures_modified': False,
        'active_bili_flow_terminal_reported_by_parent_not_independently_consumed': {
            'job': '1a1aadcfbb5-fc05-4837', 'exit_code': 1,
            'output_complete': True, 'durable': True, 'timed_out': False,
            'coordinator': {'bytes': 6332, 'sha256': '46b0fa7515c906a94924f1726f2c8f52d4c31d4d2fed3d36394fcbd586d31ada'},
            'stage': {'bytes': 1773, 'sha256': '37f6a5d54c26e4270611e8b937ed715588b2b635544a81dfdf17dfaf0af890c5'},
            'inner_first_cause_known': False, 'safe8_reader_frozen': True,
            'safe8_reader_tree': '2640c806a4a08c6863ae40f4d16b52409642e717',
        },
        'next_batch_candidates_in_order': [
            'tv.danmaku.bili', 'com.amazon.mShop.android.shopping', 'com.MobileTicket',
            'com.ihg.apps.android', 'com.bestbuy.android',
        ],
        'next_batch_is_serial_and_not_an_execution_authorization': True,
        'single_app_admission_fields_still_required_for_each_new_target': [
            'actual user/package/version/signer/base-and-split APK hashes and UID',
            'fresh Main framework epoch and held namespace/root identity',
            'preexisting task/process baseline and exact owned task lease',
            'new helper source/build/result/APK/signer/installed UID and only-state result',
            'exact target package/UID/activity/display and bounded public input plan',
            'fresh complete tree/window hash and action-bound selector',
            'unique nonces, action budget, deadlines and independent finally after-state',
        ],
        'shared_controls_that_must_remain': [
            'global action flock, same held inode, bounded pre-action admission; no foreign unlock',
            'held namespace/root entry and Main/source guards before and after every command',
            'display0/focused application/type/package/UID gates; host scope0 is not display proof',
            'whole-tree/window freshness and refreshed unique target before exactly one action',
            'fixed public input value verified inside the actual submit action-bound inspection',
            'first error retained; no action replay; after-state and cleanup run independently',
            'exact newly owned task cleanup only; preexisting task/data/account remain',
            'private trees/images stay private; published evidence contains bounded scope/hash only',
        ],
        'prohibited_implicit_expansions': [
            'Do not replace Bili constants with wildcard/list/arbitrary request package.',
            'Do not reuse Bili UID10117 or helper UID10170 for another target.',
            'Do not infer current package count182 or current version from the Nov4 snapshot.',
            'Do not turn login/captcha/location/permission/network restrictions into automatic bypass.',
            'Do not send, call, book, purchase, sign in, grant permission or change settings.',
            'Do not declare cold start without pre-launch absence evidence or kill for convenience.',
            'Do not equate frame movement/play-state with app-attributed audible output.',
            'Do not treat system/owned fixture rows as commercial business successes.',
        ],
        'whole_app_gate_policy': {
            'public_core_scope_success_is_necessary_not_sufficient': True,
            'separate_required_applicable_gates': [
                'actual core outcome and normal exit/reopen', 'cold launch when actually observable',
                'background/resume and process-restoration semantics',
                'persistence without user-data destruction',
                'network failure/recovery without altering Main network',
                'permission-denied behavior in an authorized owned domain',
                'native crash/ANR/system-server stability with exact attribution',
                'audio/camera/call/transaction outcome where applicable and separately authorized',
            ],
            'unexercised_gates_remain_open': True,
        },
        'actual_bili_local_evidence_pins_only': [file_pin(x) for x in evidence_paths],
        'reusable_code_pins_not_qualification_transfer': [file_pin(x) for x in reused],
        'apps': rows,
    }
    (HERE / 'coverage-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    counts = {}
    for row in rows:
        key=row['kind_for_planning_only'];counts[key]=counts.get(key,0)+1
    report = {
        'schema': 1, 'local_source_plan_validation_only': True,
        'matrix_sha256': MATRIX_SHA, 'reconciliation_sha256': RECON_SHA,
        'exact_package_coverage': 45, 'duplicates': 0, 'missing': [], 'extra': [],
        'historical_pending_rows': 39, 'later_scoped_records': 13,
        'planning_categories': counts,
        'all_rows_nonexecutable_and_not_qualified': all(not x['plan_executable'] and not x['whole_app_production_ready'] for x in rows),
        'Android_actions': 0, 'Hepta_calls': 0, 'Main_rescan': False,
        'coverage_plan_sha256': sha((HERE/'coverage-plan.json').read_bytes()),
    }
    (HERE/'validation-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False))

if __name__ == '__main__':
    main()
