#!/usr/bin/env python3
"""Build a plan-only 45-package acceptance catalog from the observed launcher roster."""
import copy, datetime, hashlib, json, pathlib
ROOT=pathlib.Path(__file__).resolve().parent
CATALOG=ROOT/'reference/current-native-launcher-catalog.json'
SOURCES=ROOT/'remaining_official_sources.json'
POLICY=ROOT/'regression_manifest.json'
raw=CATALOG.read_bytes(); catalog=json.loads(raw); roster=catalog['catalog']['applications']
research=json.loads(SOURCES.read_text()); sources={x['package']:x for x in research['apps']}
policy=json.loads(POLICY.read_text()); original_eight=set(policy['historical_eight_packages'])
assert len(roster)==45 and len({x['package'] for x in roster})==45 and len(original_eight)==8
by_package={x['package']:x for x in roster}
UNKNOWN={'state':'UNKNOWN_NOT_RUN','evidence_refs':[],'qualified_runtime_ref':None,'current_app_identity_ref':None}
def result():return copy.deepcopy(UNKNOWN)
def case(key,operation,steps,expected,extra=None,condition=None):
 return {'id':key,'operation':operation,'steps':steps,'expected_observable_result':expected,
         'required_evidence_profiles':['bound_action_and_readback']+(extra or []),
         'execution_condition':condition or '同一当前合格 runtime、当前安装身份和当前 helper 均已固定；相关未决动作先结算',
         'actual_result':result()}
def need(key,description,kind='test_data',authorization='在执行前验证本项所需授权'):
 return {'id':key,'kind':kind,'description':description,'availability':'UNKNOWN_NOT_SUPPLIED_BY_THIS_EVIDENCE','execution_authorization':authorization}
def account(vendor,required):
 return {'planned_mode':'authorized_login_required_for_core' if required else 'try_existing_authorized_guest_or_public_browsing_then_login_if_app_requires',
         'current_mode_observed':'UNKNOWN','login_result':result(),
         'account_requirement_for_core':'required' if required else 'conditional_on_actual_public_flow',
         'needed_account':need('account',vendor+' 的自有测试账号及正常登录/验证码渠道；不记录密码、令牌、实名材料','test_account'),
         'guest_mode_may_be_counted_only_after_actual_observation':True}
def none_account(note='本地功能没有计划中的服务账号；须由当前实际界面与组件契约确认。'):
 return {'planned_mode':'no_service_login_for_planned_local_core','current_mode_observed':'UNKNOWN','login_result':result(),
         'account_requirement_for_core':'not_planned_but_actual_contract_must_confirm','needed_account':None,'note':note}
APPS={}
def add(package,classification,auth,network,core,storage,permissions,fixtures,failures,hardware=None,notes=None,soak=None):
 assert package in by_package and package not in APPS
 item=by_package[package]
 source=sources.get(package)
 source_ref={'file':'remaining_official_sources.json','sha256':hashlib.sha256(SOURCES.read_bytes()).hexdigest(),'package':package} if source else {'file':'regression_manifest.json','sha256':hashlib.sha256(POLICY.read_bytes()).hexdigest(),'package':package}
 urls=[]
 if source:
  for k,v in source.items():
   if isinstance(v,str) and v.startswith(('https://','http://')) and v not in urls:urls.append(v)
 else:
  url=policy['apps'][package]['latest_candidate_pin'].get('source_url')
  if url:urls.append(url)
 APPS[package]={
  'package':package,'launcher_name_observed':item['name'],'launcher_component_reference':item['component'],
  'classification':classification,'historical_eight_subset':package in original_eight,
  'reference_inventory':{'observed_utc':catalog['utc'],'catalog_sha256':hashlib.sha256(raw).hexdigest(),
     'icon_key_is_not_verified_package_version':True,'cached_launcher_list_is_not_fresh_installed_package_proof':True},
  'runtime_targets':{
   'droidloom_android17_pocket4':{'state':'CURRENT_TARGET_REQUIRES_FRESH_PER_RUN_BINDING','package':package,
      'reference_epoch_sha256':catalog['guard_after']['Main_epoch_sha256'],
      'fresh_package_version_uid_signer_split_and_data_identity_required':True,
      'current_installed_version_name':'UNKNOWN_IN_THIS_PLAN','current_installed_version_code':'UNKNOWN_IN_THIS_PLAN'},
   'redroid':{'state':'RETIRED_NO_CURRENT_TEST_TARGET','current_target':None,
      'historical_package_presence':'UNKNOWN_NOT_ESTABLISHED_BY_THIS_CATALOG',
      'mapping_candidate_package_only':package,'historical_PASS_transfer_permitted':False,'new_test_result':result()}
  },
  'update_acceptance':{'source_reference':source_ref,'authoritative_source_urls_from_existing_research':urls,
     'latest_version_declared_by_this_catalog':False,'required_profiles':['current_official_artifact_and_install_identity'],
     'actual_result':result()},
  'authentication':auth,
  'core_cases':core,
  'network':{'profile':network,'app_owned_DNS_TLS_requirement':'required_for_vendor_request_path' if network in ('vendor_https','vendor_rtc','public_media','webview_https') else 'do_not_force_app_owned_DNS_TLS_without_actual_transport_applicability',
     'actual_transport_and_endpoints':'UNKNOWN','required_local_or_transport_proof':copy.deepcopy(NETWORK[network]),
     'actual_result':result()},
  'storage':{'plan':storage,'current_permission_and_storage_state':'UNKNOWN','actual_result':result()},
  'permissions':{'declared_requested_granted_and_appops_actual':'UNKNOWN',
     'permission_or_role_hints_to_inspect_not_claimed_manifest':permissions,
     'decision_rule':'读取当前完整 manifest、PM grant、app-op/角色及真实请求时机；最小功能路径和拒绝后行为均需证据，不能用预授予替代 UI 或业务验证。',
     'proactive_grants_authorized_by_this_catalog':False,'actual_result':result()},
  'hardware':{'requirements':hardware or [],'actual_capability_and_driver_state':'UNKNOWN',
     'missing_required_capability_is_a_blocker':True,'actual_result':result()},
  'test_inputs_needed':fixtures,
  'expected_failure_paths_to_exercise_or_observe':failures,
  'common_required_cases':['startup_and_current_identity','session_or_no_login_contract','permission_behavior',
      'storage_persistence','integrity_and_error_handling','long_running','app_restart','qualified_runtime_restart','fault_recovery'],
  'long_running_workload':soak or '在新提议的60分钟窗口内每5–10分钟重复本包核心路径并切换前后台；服务端限流时遵守返回的等待条件，记录实际功能读回与资源变化。',
  'new_thresholds_are_not_historical_PASS':True,
  'business_and_transaction_boundary':'只验证本表已列路径；未授权的提交订单、付款、订座、叫车、邀请、发布和对外通信仍待单独受控验收，不得由浏览页面推断已经完成。',
  'feature_contract_note':'这些是基于已知产品职责的新测试计划；当前新版本的实际资源ID、界面、权限和可用能力必须先观察，未见能力不能假写完成。',
  'notes':notes or [],
  'actual_domain_coverage':{k:result() for k in ['startup','session','core','network_or_offline_continuity','storage','permissions','hardware_if_required','integrity','long_running','app_restart','runtime_restart','fault_recovery']},
  'production_ready':False,'cleanup_eligible':False
 }
NETWORK={
 'vendor_https':{'planned_applicability':'必须验证本包实际发出的在线查询及返回；域名、TLS和业务数据须同一动作相关联。','required':['app UID/进程相关的实际请求与响应证据','实际域名解析或已验证解析缓存来源、正常TLS错误处理','查询条件与真实返回列表/详情匹配，排除只显示缓存页','3次新提议的有界断网/恢复，恢复后实际重新查询'],'not_sufficient':['宿主curl或其他App成功','首页截图','伪造服务器返回或禁用证书校验']},
 'vendor_rtc':{'planned_applicability':'账号与信令联网，文本/通话媒体须受控对端实际确认。','required':['实际账号会话的HTTPS信令与错误路径','受控文本的唯一nonce、双方接收/状态回执','实际双向通话、音频往返、正常挂断和丢网后的既定行为','按实际SDK路径记录媒体连接而不强迫将所有音频传输称为HTTPS'],'not_sufficient':['拨号界面','单方发送图标','虚构对端回执']},
 'public_media':{'planned_applicability':'真实视频/音频服务与CDN网络播放。','required':['查询与播放请求的UID相关网络证据','连续时间进度、实际视频帧变化和可听/可采样音频','暂停、继续、拖动、前后台及3次断网恢复'],'not_sufficient':['一张视频截图','封面或加载动画','禁用完整性或TLS检查']},
 'offline_local':{'planned_applicability':'本地核心应在无网络时可用；DNS/TLS不是这些本地动作的必需验收项。','required':['当前包/组件契约及实际所选本地数据源说明','在有界已确认离线条件下完成同一核心动作与读回','3次新提议的网络可用性变化期间本地功能连续；不生成DNS/TLS PASS字段','若实际启用云同步/远端文档等功能，另立必测在线分支并验证真实返回'],'not_sufficient':['写N/A或网络测试已过','仅看到INTERNET权限不存在','跳过已配置的远端功能']},
 'cellular_telephony':{'planned_applicability':'电话/SMS由Telephony、SIM或已配置合法电话账号提供；App本身不一定执行DNS/TLS。','required':['实际电话/SMS服务、可用SIM或合法已配置电话账号与框架状态','受控接收端的来电/短信/MMS回执和双向音频','飞行/无服务/重新注册等故障只在获准受控环境按实际能力验证','IMS若存在，按实际服务UID与传输记录，不把普通本地拨号UI当作联网成功'],'not_sufficient':['拨号盘能输入','没有SIM时写不适用并称全功能可用','联系未授权号码']},
 'local_search_with_delegation':{'planned_applicability':'先确认当前实际搜索provider；本地建议与委托Web搜索分开验收。','required':['实际provider与intent接收组件身份','本地结果必须来自受控可索引夹具；若没有本地provider，不能声称本地搜索通过','Web分支需接收浏览器/WebView当前身份与真实HTTPS结果；按实际承担请求的组件归属证据'],'not_sufficient':['把启动浏览器算搜索完成','将接收组件的DNS/TLS伪称搜索App自己的请求']},
 'system_settings':{'planned_applicability':'设置页和本地系统状态无需App自有DNS/TLS；所展示联网功能的实际服务另外验证。','required':['设置UI字段与受信系统读回一致','离线状态、网络恢复后状态刷新与真实服务一致','已配置账号同步、Wi-Fi或蓝牙等仅在当前硬件与授权对应分支测试'],'not_sufficient':['状态图标代替实际连通性','为了测试改变全局安全设置']},
 'thread_ipv6_lan':{'planned_applicability':'Thread受控IPv6网络、无线接口和边界路由器；普通公网DNS/TLS不是所有核心操作的前提。','required':['真实Thread能力/服务与radio驱动状态','自有测试dataset和受控border router的实际入网/邻居/连通性','按该版本实际协议验证IPv6收发与断开恢复，保留认证和网络安全设置'],'not_sufficient':['没有Thread硬件时以N/A算完成','空状态页面','关闭认证来加入网络']},
 'microg_service':{'planned_applicability':'本地设置与真正启用的GMS兼容服务分别验收；联网依赖须关联服务UID和受控调用方。','required':['当前microG源码/签名、服务列表、自检的真实结果与真实缺项','自有测试客户端对实际已启用API的正常调用和回调','已启用推送/账号/定位服务所需合法注册与服务端/受控客户端回执','服务断网/恢复后能继续正常调用；完整性拒绝保留BLOCKED'],'not_sufficient':['伪造Google/设备完整性结果','改变签名身份以通过商业App检查','把设置页打开当作服务可用']},
 'webview_https':{'planned_applicability':'当前WebView提供者、renderer和shell共同组成联网/网页执行路径。','required':['当前实际WebView提供者APK、版本、signer/平台来源及renderer身份','受控正常HTTPS页的DOM/JavaScript回读、中文输入和正常TLS错误拒绝','LocalStorage/IndexedDB/文件选择的实际读写与进程重建持久化','3次网络恢复后页面逻辑真实恢复'],'not_sufficient':['自签/错误证书绕过','只显示网页截图','把测试shell版本1等同于最新WebView实现']},
 'local_ime':{'planned_applicability':'核心中文转换、候选与提交必须可离线工作；在线词库或插件仅在实际启用时成为在线验收分支。','required':['当前IME服务与当前合格编辑器均固定身份','实际按键/候选选择→InputConnection提交→目标UTF-8文本读回','离线中文输入、前后台及焦点切换仍可用','已启用在线功能须独立真实联网证据，未启用不能伪造DNS/TLS PASS'],'not_sufficient':['通过直接写EditText绕过IME却称IME通过','跨旧epoch helper复用PASS']},
 'local_qa_contract':{'planned_applicability':'以当前已固定本地QA源码声明的探针协议为准；协议尚未取全前不猜测网络能力。','required':['实际源码/manifest/构建与helper签名、UID、epoch绑定','执行源码明确列出的本地nonce/输入/回显探针并回读','仅当源码明确存在网络探针时验证其受控端点；否则本地离线连续性单独取证'],'not_sufficient':['根据App名捏造探针返回','旧helper输出当新epoch证据','任意shell或新ADB依赖']}
}
LOCAL_STORAGE='只使用本包自有测试数据/设置，记录写入后UI或受控接口读回、正常关闭重开、3次App重启和新合格runtime中的持久化；保留UID、CE/DE目录身份，不读取或替换用户私有业务数据库。'
REMOTE_STORAGE='记录测试查询/筛选和允许持久化的会话状态，正常退出重进后核对；缓存与实时服务数据分开标明，不能以缓存页面冒充网络成功；升级前后保留UID和CE/DE数据身份。'
BASE_FAIL=['冷启动/Activity无法解析、崩溃或ANR','权限被拒后的明确可恢复行为','磁盘/缓存写入失败后的错误与数据保全','App进程退出后重新进入的实际恢复；不自动抹数据','完整性、安全或账号限制必须按真实拒绝保留BLOCKED']
LOC_HINT=['INTERNET（按实际manifest）','ACCESS_NETWORK_STATE（若声明）','通知（若该版本请求）','定位只核对现有授权；手动城市/地址为首选']
def hotel(pkg,vendor,member):
 core=[case('hotel_search','手动城市/日期酒店搜索',['输入受控城市、入住/离店日期与人数','查看实时结果并改变一个筛选条件'],'返回酒店名称、位置、可售日期与与筛选一致的列表',['vendor_response']),
       case('rate_conditions','房型、价格和取消条件读回',['打开一间真实可售酒店','展开房型、币种、税费与取消条件'],'房型/日期/人数、价格和条款读回一致；返回列表状态保留',['vendor_response']),
       case('member_session',member+'账号会话',['若核心路径要求会员则使用已授权账号正常登录','查看会员页面并退出重进；不输出会员敏感数据'],'真实登录状态和访问权限符合服务返回，不把登录页当成功',['authorized_session'],condition='已提供授权测试账号；若公开路径无需会员，记录实际公开模式，会员功能仍是单独UNKNOWN')]
 add(pkg,'third_party_commercial',account(vendor,pkg=='com.Hyatt.hyt'),'vendor_https',core,REMOTE_STORAGE,LOC_HINT,
     [need('hotel_fixture',vendor+' 的可查询城市/酒店、日期/人数及会员方案范围'),need('member_account',member+'自有测试账号','test_account')],
     BASE_FAIL+['城市/日期无库存、会话过期、地区/币种错误、TLS或服务错误'],
     notes=['订房、数字钥匙和真实入住能力若属于最终使用范围，必须补有授权的受控预订/酒店端条件；本计划不凭房价页面声称这些能力完成。'])
def flight(pkg,vendor):
 core=[case('flight_search','航班和票价查询',['手动选择合法出发/到达机场、未来日期、人数与舱位','查询并查看实际航班/票价条件'],'航班号、起降时间/机场、币种、税费/退改条件与查询一致',['vendor_response']),
       case('flight_status','航班动态查询',['输入受控航班号与日期','读取计划/实际时间、航站信息和状态'],'实际服务返回的日期/航班匹配，明确区分无结果和网络失败',['vendor_response']),
       case('search_state','查询状态与导航恢复',['打开票价/行程详情再返回','切换前后台并重开查询'],'查询条件和当前列表可继续使用，过期价格按服务要求刷新',['storage_readback'])]
 add(pkg,'third_party_commercial',account(vendor,False),'vendor_https',core,REMOTE_STORAGE,LOC_HINT+['相机/媒体仅扫码或文件功能实际请求时检查'],
     [need('flight_fixture',vendor+'的出发/到达机场、可查询航班号/日期和合法查询范围'),need('member_account',vendor+'会员账号（登录或行程管理分支）','test_account')],
     BASE_FAIL+['无航班/售罄、航班日期错误、服务超时、会话过期、航班详情打不开'],
     notes=['值机、证件核验、真实订单/登机牌需另有自有测试订单和授权；不伪造身份或提交真实机票购买。'])
def retail(pkg,vendor,query,fields):
 core=[case('product_search','中文/英文商品搜索和筛选',['输入受控关键词：'+query,'改变实际存在的排序或筛选项'],'列表与查询/筛选一致，标题、商家与价格可以真实读取',['vendor_response']),
       case('product_detail','商品详情与规格读回',['打开受控商品','切换实际存在的规格并读取'+fields],'规格、库存/配送限制与真实服务结果对应，不能只验证图片',['vendor_response']),
       case('reversible_cart','自有测试购物车或收藏状态',['仅在账号和该可逆动作已获准时加入一件测试商品/收藏','核对数量/规格后恢复该测试项原状'],'UI与服务读回一致；未授权登录/服务器状态写入则此项保持UNKNOWN',['authorized_session','storage_readback'],condition='自有测试账号及可逆服务器测试数据操作已明确授权；不结算、不联系商家')]
 add(pkg,'third_party_commercial',account(vendor,False),'vendor_https',core,REMOTE_STORAGE,LOC_HINT+['相机/媒体只在实际选择扫码或上传分支时检查'],
     [need('product_fixture',vendor+'当时存在的受控商品/SKU、关键词和配送地区'),need('account',vendor+'自有测试账号（购物车/收藏分支）','test_account')],
     BASE_FAIL+['商品下架/规格无货、地区/配送地址不匹配、请求超时、登录挑战或完整性拒绝'],
     notes=['支付、真实购买、评价和商家联系未在本计划执行授权内；若最终验收包含这些能力，必须有受控交易条件。'])
def rental(pkg,vendor):
 core=[case('rental_search','手动网点及取还车查询',['选手动城市、取车/还车网点和未来时间','查询车辆并读取可租列表'],'网点/时间/车组与服务返回一致，不能用定位失败遮盖手动流程',['vendor_response']),
       case('vehicle_terms','车型报价与条款',['打开真实车组报价','读取里程、保险、押金/费用和年龄/证照条件'],'报价单位、币种、期间与条款真实可读，不提交预订',['vendor_response']),
       case('rental_navigation','返回修改与持久化',['返回修改时间或网点并重新查','切前后台再打开详情'],'结果刷新且旧查询不冒充新报价',['storage_readback','vendor_response'])]
 add(pkg,'third_party_commercial',account(vendor,False),'vendor_https',core,REMOTE_STORAGE,LOC_HINT,
     [need('rental_fixture',vendor+'受控城市/网点、日期和合法年龄条件'),need('account',vendor+'自有会员账号（若真实流程要求）','test_account')],
     BASE_FAIL+['网点无车辆、跨时区/跨日错误、会话过期、网络中断和报价页异常'],
     notes=['真实预订、押金、驾驶资格核验和取车不由查询结果代替；需要自有受控订单及另行授权。'])
def ride(pkg,vendor):
 core=[case('manual_route','手动起终点与路线',['在已授权账号中手动输入受控起点/终点','核对地图标记、地址消歧与路线'],'起终点和服务地址一致，定位被拒时仍显示明确可操作状态',['vendor_response']),
       case('fare_preview','车型、预估费用和等待时间',['选择实际存在的车型','读取价格/预估到达和付款方式页面的非敏感字段'],'报价与受控路线对应，按钮前止步；不创建真实叫车请求',['vendor_response']),
       case('route_recovery','路线编辑和丢网恢复',['修改目的地后回读','有界断网恢复后重新请求报价'],'没有把旧报价误用于新路线，错误可恢复',['vendor_response','storage_readback'])]
 add(pkg,'third_party_commercial',account(vendor,True),'vendor_https',core,REMOTE_STORAGE,LOC_HINT+['电话/通讯录仅实际功能明确需要时检查'],
     [need('account',vendor+'合法地区的自有测试账号及正常验证渠道','test_account'),need('route_fixture','受控真实可服务地址对；不使用他人家庭地址')],
     BASE_FAIL+['地区不可用、手动地址歧义、无车、定位拒绝、完整性或登录限制'],
     hardware=[{'capability':'地图/图形呈现；若实际范围要求GPS，则需原有合法定位路径','required':'conditional_on_actual_location_scope','current_evidence':'UNKNOWN'}],
     notes=['不得伪造位置规避地区限制；本计划手动地址路径不主动授予定位。真实派单或联系司机必须另行受控授权。'])
def communications(pkg,vendor,video=False):
 core=[case('login_session','合法账号登录和会话恢复',['使用已授权自有账号按原服务正常登录','重开应用并验证会话；不记录验证码/密钥'],'账号真实登录、必要号码/地区条件满足，保护或完整性拒绝保持BLOCKED',['authorized_session']),
       case('controlled_text','受控文本双向收发',['仅在明确通信授权和自有对端均落实后发送唯一测试nonce','由受控对端确认收取并回复新的nonce'],'发送/接收时间、内容和状态双方一致，不能由本方图标推断送达',['controlled_peer_receipt'],condition='明确通信授权、账号与受控对端均提供；没有这些输入不得发送'),
       case('controlled_call','受控通话连接、音频与挂断',['仅呼叫明确授权的自有测试对端','双方检查双向音频并正常挂断；记录来电/后台通知'],'对端连接记录和双方音频往返真实存在；拨号页不是成功',['controlled_peer_receipt','media_hardware'],condition='明确呼叫授权和受控对端；不得拨打真实无关号码或紧急号码')]
 if video:core.append(case('controlled_attachment','受控附件/语音或视频会话',['只选择预置无个人信息的测试文件或测试音频','在受控对端回读文件hash或双向媒体'],'实际传输与显示一致，权限拒绝不崩溃',['controlled_peer_receipt','storage_readback'],condition='本版本实际支持所选能力，受控对端与发送授权明确'))
 add(pkg,'third_party_commercial',account(vendor,True),'vendor_rtc',core,REMOTE_STORAGE,
     ['INTERNET及实际媒体网络能力','RECORD_AUDIO（实际通话）','通知/后台来电状态','相机仅受控视频功能','通讯录/电话/媒体按实际manifest与用户选择'],
     [need('account',vendor+'自有合法测试账号、可用号码/地区和正常验证渠道','test_account'),
      need('controlled_peer',vendor+'的自有测试号码或自有受控账号；需记录测试接收方明确同意','controlled_peer','尚未由本计划授予对外发送/呼叫权限，执行前须另有明确授权'),
      need('audio_loopback','双方可确认的测试音频/录音回环方案，无旁人录音','hardware_fixture')],
     BASE_FAIL+['地区/注册限制、登录挑战、号码不可用、送达超时、NAT/媒体失败、后台来电丢失'],
     hardware=[{'capability':'麦克风、扬声器与音频路由；视频另需相机','required':'audio_required_video_conditional','current_evidence':'UNKNOWN'}],
     notes=['账号被封、Play/商业完整性拒绝不能通过伪造环境、签名或检查结果修复。'],
     soak='新提议60分钟真实在线/后台待机；在已授权计划内的有限时点由受控对端触发文本/来电，记录通知及收发。通话时长独立限定，不能默认持续收费呼叫60分钟。')

hotel('com.Hyatt.hyt','Hyatt','World of Hyatt')
hotel('com.hilton.android.hhonors','Hilton','Hilton Honors')
hotel('com.ihg.apps.android','IHG','IHG One Rewards')
hotel('com.marriott.mrt','Marriott','Marriott Bonvoy')
for p,v in [('com.rytong.airchina','中国国航'),('com.rytong.ceair','东方航空'),('com.united.mobile.android','United Airlines'),('jp.co.ana.android.tabidachi','ANA')]:flight(p,v)
for p,v in [('com.ehi.national.mobile','National'),('com.hertz.android.digital','Hertz'),('com.szzc','神州租车')]:rental(p,v)
for p,v,q,f in [('com.amazon.mShop.android.shopping','Amazon Shopping','受控商品英文关键词','币种、配送与库存'),
 ('com.bestbuy.android','Best Buy','受控电子产品型号','配置、库存与自取/配送门店'),
 ('com.jingdong.app.mall','京东','受控商品中文关键词','规格、库存与配送'),
 ('com.taobao.taobao','淘宝','受控商品中文关键词','规格、商家与配送'),
 ('com.xunmeng.pinduoduo','拼多多','受控商品中文关键词','规格、实际购买类型与费用')]:retail(p,v,q,f)
ride('com.sdu.didi.psnger','滴滴');ride('com.ubercab','Uber')
communications('com.enflick.android.TextNow','TextNow')
communications('com.pinger.textfree','TextFree')
communications('com.tencent.mm','微信',True)
add('com.MobileTicket','third_party_commercial',account('铁路12306',False),'vendor_https',
 [case('train_search','车次、座席与票价查询',['手动选出发/到达站、合法预售日期','查看车次、席别及余票状态并改一次筛选'],'站名/日期与实际列表一致，明确区分无票和失败',['vendor_response']),
  case('train_detail','列车时刻与经停信息',['打开受控车次详情','查看经停站、到发时刻、票价/席别'],'真实详情与车次/日期对应，不提交订单',['vendor_response']),
  case('rail_session','正常登录/乘车资料边界',['账号功能如要求登录则使用自有测试账号','仅核对会话成功与测试资料范围，不导出实名/证件数据'],'身份校验/验证码按原流程；没有账号或授权则保持UNKNOWN',['authorized_session'],condition='合法自有12306账号与该资料访问授权')]
 ,REMOTE_STORAGE,LOC_HINT+['相机/证件功能仅在另有合法测试资料时'],
 [need('rail_fixture','受控车次、车站与当前可查询日期'),need('rail_account','合法实名自有测试账号；不虚构实名资料','test_account')],
 BASE_FAIL+['余票为空、预售日期越界、实名/验证码校验、登录过期和请求失败'],
 notes=['购票、改签、退票、刷脸和真实乘车均不能由查询页面代替；需独立授权和受控订单。'])
add('com.lianjia.beike','third_party_commercial',account('贝壳',False),'vendor_https',
 [case('chinese_listing_search','中文房源查询',['手动选择城市','通过现有中文输入链输入受控小区/区域关键词并查询'],'真实房源列表和中文查询一致，定位拒绝不阻断手动流程',['vendor_response','ime_commit']),
  case('listing_filter_detail','筛选与房源详情',['更改价格/户型等实际筛选项','打开一套房源查看基本资料、图片及位置描述'],'列表/详情字段互相对应且实际可交互',['vendor_response']),
  case('search_persistence','新版本查询持久化',['返回列表并切前后台','重开后核对允许保存的城市/筛选状态'],'升级后仍保留UID/数据目录和正常可用状态',['storage_readback'])]
 ,REMOTE_STORAGE,LOC_HINT+['媒体访问仅已选择的上传功能'],
 [need('housing_fixture','明确城市、小区/区域关键词及允许读取的公开房源')],
 BASE_FAIL+['旧版升级未结算、UID或数据目录改变、中文输入不提交、房源列表空白、详情图失败'],
 notes=['执行前必须使用 root 当前 Beike 安装流程的最终结算；本计划不猜测 r2 是否已完成。不得联系经纪人或预约看房。'])
add('com.zillow.android.streeteasy','third_party_commercial',account('StreetEasy',False),'vendor_https',
 [case('nyc_listing_search','手动区域/地址房源搜索',['输入受控纽约区域或公开房源地址','设置租/售与价位/卧室筛选'],'实际区域、租售类别与房源列表一致',['vendor_response']),
  case('map_listing_detail','地图与房源详情联动',['切换列表/地图','打开公开房源并核对地址、价格、图片和详情'],'地图点与详情对应，缩放/返回无错误',['vendor_response']),
  case('saved_search','可逆保存搜索',['仅在自有账号和保存操作授权具备时保存测试搜索','重开核对后清掉该测试项'],'保存状态由实际服务回读，不发送经纪人咨询',['authorized_session','storage_readback'],condition='自有账号和可逆服务器测试项授权')]
 ,REMOTE_STORAGE,LOC_HINT,[need('listing_fixture','受控纽约地区/公开房源查询'),need('account','StreetEasy自有测试账号（保存分支）','test_account')],
 BASE_FAIL+['地区/地址消歧失败、地图空白、详情加载失败、会话失效'],
 notes=['不提交联系表、不打电话、不预约。'])
add('com.sankuai.meituan.takeoutnew','third_party_commercial',account('美团外卖',False),'vendor_https',
 [case('manual_service_address','手动城市/配送地址',['保持现有FINE/COARSE权限状态','手动输入受控可配送地址并核对服务范围'],'手动地址被真实接受；定位拒绝不会被主动grant覆盖',['permission_snapshot','ime_commit']),
  case('shop_menu','商家与菜单查询',['中文搜索受控商家/菜品','打开实际营业商家菜单并读取规格/价格'],'商家、配送范围、营业状态与菜单实际一致',['vendor_response']),
  case('reversible_test_cart','可逆测试购物车',['在实际允许的访客/账号状态下选择一项测试菜品','读取规格、数量和费用后恢复测试购物车'],'购物车读回与选项一致，未提交订单或付款',['storage_readback','vendor_response'])]
 ,REMOTE_STORAGE,['FINE/COARSE定位基线只读；禁止主动grant','INTERNET与网络状态','通知按实际请求','存储/相机只在实际可选功能需要时'],
 [need('delivery_fixture','受控可配送的测试地址与商家/菜品；不得使用未授权他人地址')],
 BASE_FAIL+['手动地址不可用、位置权限被擅自打开、商家不配送/闭店、菜单/购物车错误'],
 notes=['禁止主动授予 android.permission.ACCESS_FINE_LOCATION 或 ACCESS_COARSE_LOCATION；前后完整权限/app-op快照必须相等或仅记录已授权真实变化。'])
APPS['com.sankuai.meituan.takeoutnew']['permissions']['forbidden_proactive_grants']=['android.permission.ACCESS_FINE_LOCATION','android.permission.ACCESS_COARSE_LOCATION']
add('com.zhubajie.client','third_party_commercial',account('猪八戒',False),'vendor_https',
 [case('brand_and_route','实际应用身份与启动品牌核对',['对照官方来源、包名和签名固定本次安装','观察Launcher异常标签与打开后的真实品牌/主界面'],'必须确认是正确官方猪八戒应用；不能把ExpandableTextViewLibrary标签当作已经修好',['official_artifact']),
  case('service_search','中文服务搜索',['搜索受控服务词，例如平面设计','选择实际存在的服务分类/筛选'],'真实服务列表与中文查询一致',['vendor_response','ime_commit']),
  case('service_detail','服务商/作品与条款详情',['打开一个公开服务条目','读取作品/服务说明、公开报价与条款'],'详情和列表对应；不联系服务商或发布需求',['vendor_response'])]
 ,REMOTE_STORAGE,LOC_HINT,[need('service_fixture','允许读取的公开服务分类/关键词')],
 BASE_FAIL+['实际品牌/签名不匹配、异常label、服务详情空白、登录挑战'],
 notes=['已观察到Launcher标签为 ExpandableTextViewLibrary；这里只登记待查问题，不推断该包已损坏或已修复。'])
add('ctrip.android.view','third_party_commercial',account('携程',False),'vendor_https',
 [case('hotel_query','酒店查询',['手动城市/入住离店日期/人数','打开真实酒店房型与退改条件'],'列表、酒店、房型、费用与日期一致',['vendor_response']),
  case('flight_query','航班查询',['手动出发/到达城市和日期','打开实际航班与票价条件'],'航班/时间/机场与价格读回一致',['vendor_response']),
  case('rail_query','火车票查询',['选出发到达站及合法日期','读取车次、席别与余票状态'],'返回与站名/日期一致，空库存与网络错误分开',['vendor_response'])]
 ,REMOTE_STORAGE,LOC_HINT,[need('travel_fixture','酒店、航班、铁路各一组受控公开查询条件'),need('account','携程自有测试账号（需要登录的分支）','test_account')],
 BASE_FAIL+['多个服务标签间状态混淆、陈旧价格、单服务网络异常、登录/完整性限制'],
 notes=['多业务App不以酒店一页成功覆盖航班/铁路；实际启用但尚未列入验收的业务保留待确定范围。'])
for package,vendor in [('com.ss.android.ugc.aweme','抖音'),('tv.danmaku.bili','哔哩哔哩')]:
 add(package,'third_party_commercial',account(vendor,False),'public_media',
  [case('public_video_search','中文公开视频搜索',['仅使用当前允许的合法访客或账号会话','通过现有中文输入查询受控公开视频主题'],'实际返回可打开的公开视频条目',['vendor_response','ime_commit']),
   case('playback_controls','真实音视频播放',['播放受控公开视频并观察连续帧/时间/音频','暂停继续、拖动并切前后台'],'视频帧和音频真实推进，控制后继续播放，不能只凭截图',['media_hardware','vendor_response']),
   case('playback_recovery','网络中断与播放器恢复',['在受控网络条件下暂停可用性','恢复连接后按实际UI继续播放'],'有明确错误/重试状态，恢复后真实媒体继续，不循环加载',['media_hardware','vendor_response'])]
  ,REMOTE_STORAGE,['INTERNET与网络状态','媒体/存储仅离线缓存或上传的实际请求','麦克风/相机不为普通观看主动开启','通知按实际请求'],
  [need('video_fixture','公开且允许播放的测试视频/关键词与可确认音轨'),need('account',vendor+'自有测试账号或已确认的合法访客会话','test_account')],
  BASE_FAIL+['访客/隐私流程被阻断、完整性拒绝、黑屏/静音、解码失败、循环缓冲'],
  hardware=[{'capability':'实际视频解码/显示和音频输出','required':'required','current_evidence':'UNKNOWN'}],
  soak='新提议连续60分钟公开视频播放，周期性暂停/继续和前后台切换；记录实际帧、进度、音频、ANR/崩溃与资源；不以封面静帧代表播放。')
APPS['tv.danmaku.bili']['notes']+=['历史 Accept 仅限 p4-bili-m30-cell-20261010 的独立测试授权，不能转给 Main/生产或新epoch；本计划所有 Bili Accept 操作数为0。','此前未决 launch/task 结果必须按原所有权证据结算；不得重写为未发生或套用旧PASS。']
APPS['tv.danmaku.bili']['authorization_boundary']={'historical_accept_cell':'p4-bili-m30-cell-20261010','historical_accept_is_production_authorization':False,'Accept_executions_authorized_by_this_catalog':0}

add('com.android.calendar','framework_owned_AOSP_component',none_account(),'offline_local',
 [case('local_event_crud','本地测试事件创建/修改',['先确认一个允许写入的本地或受控测试日历','创建唯一nonce标题的事件，修改时间并重新打开'],'只该测试事件的标题/时间/时区读回一致，不发送邀请',['provider_readback']),
  case('calendar_views','日/周/月切换与提醒',['查看该事件在实际日/周/月视图的位置','在获准测试提醒条件下验证通知/时间触发'],'事件日期映射正确；提醒需要实际通知/时钟证据',['notification_delivery']),
  case('event_persistence','进程重建后事件持久化',['正常关闭重开和新合格runtime后定位测试事件','最后仅清理此明确归属的测试事件'],'事件ID/字段保持，其他真实日历数据未改',['provider_readback','storage_readback'])]
 ,LOCAL_STORAGE,['READ_CALENDAR/WRITE_CALENDAR或实际系统授权','通知与提醒相关角色/权限按实际manifest'],
 [need('calendar_fixture','独立本地测试日历或自有测试云日历；明确不包含受邀者')],
 BASE_FAIL+['无可写本地日历、日历provider失败、时区偏移、提醒丢失、云同步账号失效'],
 notes=['云同步仅在实际配置为范围内时追加真实账号/同步服务证据；本地日历不强制DNS/TLS PASS。'])
add('com.android.camera2','framework_owned_AOSP_component',none_account(),'offline_local',
 [case('photo_capture','真实相机取景和拍照',['先识别当前camera provider和实际可用设备','对受控测试场景取景/拍照并打开所存照片'],'实际相机帧、保存URI、尺寸/时间与照片解码对应，不能用截图替代相机',['media_hardware','media_store_readback']),
  case('video_record','短视频和音频录制',['按实际支持模式录制受控场景/音轨','正常停止，打开视频并回放'],'保存视频可解码、时长和音频与采集对应',['media_hardware','media_store_readback']),
  case('camera_recovery','相机占用/权限与生命周期',['按获准测试条件观察相机不可用或权限拒绝','释放受控占用或恢复合法条件后重新打开'],'错误明确、资源释放，重新取景/拍照实际成功',['media_hardware'])]
 ,LOCAL_STORAGE+' 相片/视频写入正常MediaStore或SAF测试位置，核对URI、大小/编码信息及可读性。',['CAMERA','RECORD_AUDIO（录像有音轨）','按当前Android目标使用MediaStore/媒体访问，禁止以全盘权限替代'],
 [need('camera_scene','无个人信息的真实可见测试场景/测试图案','hardware_fixture'),need('camera_device','已配置合法相机设备/provider','hardware_fixture')],
 BASE_FAIL+['没有相机HAL/设备、黑帧、相机占用、录像音轨缺失、MediaStore写入失败'],
 hardware=[{'capability':'实际camera provider/设备、图像帧与视频编码；有声录像另需麦克风','required':'required','current_evidence':'UNKNOWN'}],
 notes=['没有相机硬件不能标N/A后宣称Camera可用；保留为硬件能力阻断。'])
add('com.android.contacts','framework_owned_AOSP_component',none_account(),'offline_local',
 [case('contact_crud','本地中文测试联系人',['选择本地或受控测试账号的联系人存储','创建唯一nonce中文姓名并编辑一个非敏感字段'],'创建/搜索/编辑读回一致，只操作合成联系人',['provider_readback','ime_commit']),
  case('vcard_roundtrip','受控vCard导入/导出',['用正常SAF选择受控vCard并导入','只导出该测试联系人到自有测试目录'],'姓名与字段保真、重复处理明确、文件可回读',['scoped_file_roundtrip']),
  case('contact_persistence','重启后联系人和权限拒绝行为',['正常重开核对合成联系人','在获准条件下观察权限拒绝/恢复路径'],'数据仍在，错误不破坏已有联系人',['provider_readback'])]
 ,LOCAL_STORAGE,['READ_CONTACTS/WRITE_CONTACTS或实际系统授权','SAF单文件URI授权'],
 [need('contact_fixture','只包含合成姓名和自有测试号码的vCard/联系人；明确本地存储目的地')],
 BASE_FAIL+['没有可写联系人账户、导入编码错误/重复、provider异常、权限拒绝'],
 notes=['不浏览或导出用户真实通讯录；云同步若已配置且在最终范围内要单独受控验证。'])
add('com.android.deskclock','framework_owned_AOSP_component',none_account(),'offline_local',
 [case('timer_alarm','受控定时器与闹钟',['创建短时测试定时器和获准的测试闹钟','记录实际触发时刻、通知/音频，并按UI停止'],'触发、停止与界面状态一致，不能只看到已设置标签',['notification_delivery','media_hardware']),
  case('stopwatch','秒表计时和前后台',['开始秒表并记录单调时钟参照','切换前后台，暂停/继续并读回'],'计时连续，无异常归零/明显漂移；实际误差须量测',['monotonic_timing']),
  case('alarm_restart','重开/重启后闹钟状态',['正常App重开及合格runtime重启后读取测试闹钟','按系统实际精确闹钟/电池策略验证触发'],'保存设置与触发策略一致，仅恢复/删除自有测试闹钟',['notification_delivery','storage_readback'])]
 ,LOCAL_STORAGE,['通知','精确闹钟能力/实际SCHEDULE_EXACT_ALARM或系统授权','音频输出与后台调度'],
 [need('alarm_fixture','允许发声的短测试窗口和自有测试闹钟标签')],
 BASE_FAIL+['AlarmManager不可用、通知被拒、后台触发丢失、时区/时钟跳变、无音频'],
 hardware=[{'capability':'系统时钟/单调时钟、AlarmManager和用户可确认音频/通知','required':'required','current_evidence':'UNKNOWN'}],
 soak='新提议60分钟秒表/受控计时，前后台周期采样并与单调时钟比对；量测漂移、通知延迟、重开后的状态。')
add('com.android.dialer','framework_owned_AOSP_component',none_account('电话账号/SIM是服务前提，不是网络会员登录。'),'cellular_telephony',
 [case('dialpad_and_role','拨号输入和电话角色',['核对实际默认/可用电话账号与拨号组件','只输入受控测试号码并更正数字，未授权前不呼出'],'拨号盘、格式化和账号状态正确；输入成功不等于通话成功',['permission_snapshot']),
  case('controlled_voice_call','受控语音呼出/呼入',['有明确授权后向自有对端呼叫并接收对端回拨','确认双向音频、静音/扬声器（若支持）和挂断'],'双方真实呼叫/音频与Telephony状态一致',['controlled_peer_receipt','media_hardware'],condition='合法SIM/电话账号、受控对端和明确呼叫授权均具备'),
  case('call_history','自有测试通话记录',['只查看该自有测试通话的记录','重开后核对时间、方向和状态'],'自有记录一致，不遍历真实用户通话历史',['provider_readback'])]
 ,LOCAL_STORAGE,['电话/默认Dialer角色','CALL_PHONE/READ_PHONE_STATE及呼叫日志按实际系统契约','RECORD_AUDIO/音频路由按实际通话栈'],
 [need('telephony_service','合法已配置SIM/电话账号及正常服务','hardware_fixture'),need('controlled_peer','自有测试号码和明确呼叫授权','controlled_peer','无明确授权不得呼叫')],
 BASE_FAIL+['无SIM/无电话账号/无Telephony、无服务、权限或角色失败、单向音频、断线后状态残留'],
 hardware=[{'capability':'真实可用telephony service、合法SIM/电话账号、麦克风与扬声器','required':'required_for_voice_core','current_evidence':'UNKNOWN'}],
 notes=['不存在电话能力应保留BLOCKED_HARDWARE，不能用拨号UI通过替代核心通话。'])
add('com.android.documentsui','framework_owned_AOSP_component',none_account(),'offline_local',
 [case('test_file_operations','自有测试文件创建/复制/重命名',['通过正常文档UI进入自有测试目录','对预置UTF-8文本与二进制文件复制/重命名并重新打开'],'路径/显示名、文件大小和内容hash对应，只操作自有夹具',['scoped_file_roundtrip']),
  case('saf_grant','SAF选择/取消与URI权限',['从受控客户端打开文件/目录选择器','选择测试项并核对授予URI、取消路径和重开访问'],'客户端能访问选择范围，越界访问拒绝，取消不产生虚假选择',['scoped_file_roundtrip','permission_snapshot']),
  case('storage_failure','只读/不可用文档provider',['使用明确受控的只读/短暂不可用provider夹具','观察错误并恢复后重开测试文件'],'错误不破坏原文件，恢复后真实读回',['scoped_file_roundtrip'])]
 ,LOCAL_STORAGE+' 仅SAF/文档provider正常路径；不能读其他App私有数据或申请MANAGE_EXTERNAL_STORAGE来让测试通过。',
 ['SAF URI读写/持久授权和实际文档provider','不主动添加全盘文件权限'],
 [need('document_fixture','自有测试目录、已知hash的UTF-8/二进制文件、受控只读provider')],
 BASE_FAIL+['文档provider崩溃、URI授权过期、中文文件名损坏、只读/磁盘满错误、文件损坏'],
 notes=['远端文档provider只在实际安装/配置并纳入范围时额外验证；本地文件操作不强制DNS/TLS。'])
add('com.android.gallery3d','framework_owned_AOSP_component',none_account(),'offline_local',
 [case('media_browse','测试照片/视频枚举与解码',['只选取预置合成照片和短视频集合','打开缩略图/详情、放大图片并播放视频'],'MediaStore URI、尺寸/方向/时长与实际解码/音轨一致',['media_store_readback','media_hardware']),
  case('media_edit','实际支持的可逆图片编辑',['仅当当前版本提供编辑时对测试照片执行旋转/裁剪并另存','重新打开新副本并核对预期尺寸/方向'],'只影响自有测试副本；原文件hash保持',['scoped_file_roundtrip'],condition='当前版本实际有该功能；缺失需依据产品契约判定，而不是自动写N/A'),
  case('scoped_share','受控接收组件的URI分享',['选择合成媒体并仅分享给自有受控接收helper','核对URI读权限与到期行为'],'接收helper读到同一测试媒体，未发送到外部账号',['scoped_file_roundtrip','permission_snapshot'])]
 ,LOCAL_STORAGE+' 使用正常MediaStore/SAF，合成原始媒体与编辑副本分别记录hash。',['当前目标Android对应的媒体访问权限/照片选择器','分享URI授权'],
 [need('media_fixture','已知hash/方向/尺寸的无个人信息图片和带测试音轨短视频'),need('share_receiver','同epoch已资格化的自有URI接收helper','controlled_local_peer')],
 BASE_FAIL+['缩略图和真实媒体不一致、解码失败、旋转异常、权限拒绝、分享URI不可读'],
 hardware=[{'capability':'显示/媒体解码、视频音轨输出','required':'required_for_declared_media_core','current_evidence':'UNKNOWN'}])
add('com.android.messaging','framework_owned_AOSP_component',none_account('SMS/MMS依赖合法SIM/电话服务和默认消息角色。'),'cellular_telephony',
 [case('sms_draft','合成短信草稿与输入',['只选择受控测试号码，输入唯一nonce中文草稿','保存草稿并重开，未授权时不发送'],'草稿/号码正确持久化，不误发',['ime_commit','storage_readback']),
  case('controlled_sms','受控SMS收发',['明确授权后发送测试nonce','由自有SIM/号码对端确认并回复另一个nonce'],'双向实际接收和Telephony/provider记录一致',['controlled_peer_receipt','provider_readback'],condition='合法可用SIM、消息角色、受控对端和明确发送授权'),
  case('controlled_mms','实际启用MMS附件收发',['如果当前部署宣称MMS可用，选择合成小图片','由受控对端确认内容和收取状态'],'内容与对端回执对应，APN/媒体失败不伪装成功',['controlled_peer_receipt','media_store_readback'],condition='MMS在实际配置/功能范围中，且受控发送授权具备')]
 ,LOCAL_STORAGE,['默认SMS角色与实际READ/RECEIVE/SEND_SMS授权','通知','按实际MMS分支的媒体/URI授权'],
 [need('telephony_service','合法SIM、SMS/MMS服务与必要正常运营商配置','hardware_fixture'),need('controlled_peer','自有测试SMS号码及明确文本/附件发送授权','controlled_peer','未具备时不可发送')],
 BASE_FAIL+['无Telephony/无SIM、默认消息角色错误、发送失败/未送达、MMS APN失败、草稿丢失'],
 hardware=[{'capability':'实际Telephony与合法SMS服务；MMS按实际范围另需数据服务','required':'required_for_sms_core','current_evidence':'UNKNOWN'}])
add('com.android.quicksearchbox','framework_owned_AOSP_component',none_account(),'local_search_with_delegation',
 [case('query_input','中文/英文查询输入与编辑',['先读取当前实际搜索provider/接收组件','通过现有IME输入唯一查询并编辑/清空'],'查询文本与UTF-8读回一致；不猜测未安装搜索后端',['ime_commit']),
  case('search_results','实际本地provider或Web搜索结果',['按当前真实provider搜索受控可索引夹具或公开查询','若委托Web则绑定接收组件并读取真实结果'],'结果与query对应；必须说明由哪个组件执行，不以intent发出当成功',['provider_readback','delegated_component']),
  case('search_navigation','建议、取消与返回',['打开一条实际存在的建议/结果','返回并检查查询/焦点状态'],'目标路由与选择对应，取消/无结果路径可恢复',['bound_action_and_readback'])]
 ,LOCAL_STORAGE,['按实际搜索provider的本地权限','委托Web组件的网络能力单独绑定'],
 [need('search_provider','当前实际搜索provider和可查询自有夹具或允许的Web查询')],
 BASE_FAIL+['缺少搜索provider、intent无接收者、IME无法提交、结果空白、Web分支网络失败'],
 notes=['未知本地provider不能被虚构成联系人搜索；如果仅提供Web搜索，则其实际Web结果是核心必测项。'])
add('com.android.settings','framework_owned_AOSP_component',none_account(),'system_settings',
 [case('about_and_app_info','系统与应用详情读回',['打开关于系统和指定测试App详情','将显示的系统/版本、存储/权限摘要与受信读取对照'],'显示字段与当前实际runtime/App身份一致，不能显示旧epoch数据',['system_service_readback']),
  case('permission_navigation','权限页面与现有状态',['进入当前应用权限/通知设置','只读核对，特别核对美团定位未被主动打开'],'UI与PM/app-op/角色现有状态对应；不主动改变安全约束',['permission_snapshot']),
  case('network_storage_status','网络/存储状态页面',['查看当前网络与存储页面','在已授权的统一故障恢复测试中观察状态刷新'],'展示与真实系统服务一致，离线仍可查看本地设置',['system_service_readback'])]
 ,LOCAL_STORAGE,['系统Settings原有权限和角色；不追加特权','美团FINE/COARSE只读','权限切换测试须独立范围授权'],
 [need('settings_reference','当前合格runtime、测试App PM身份和可验证系统服务状态')],
 BASE_FAIL+['页面/Settings provider崩溃、展示旧状态、权限显示与真实grant不一致、网络状态不刷新'],
 notes=['不得关闭完整性、防护或扩大权限来让其他App通过；这个测试计划不授权全局设置变更。'])
add('com.android.threadnetwork.demoapp','framework_owned_AOSP_demo',none_account(),'thread_ipv6_lan',
 [case('thread_capability','真实Thread服务/设备识别',['打开实际Thread演示页','读取服务状态和权限失败，与原系统能力读回对照'],'有真实Thread服务和接口；缺失是能力阻断',['system_service_readback','hardware_capability']),
  case('controlled_thread_join','自有Thread网络入网',['仅使用自有测试dataset和边界路由器','按该版本正常流程加入并读取状态'],'真实入网/邻居/地址状态与受控路由器记录一致',['controlled_peer_receipt'],condition='真实硬件/服务、合法测试dataset和明确入网授权'),
  case('thread_recovery','受控IPv6连通与故障恢复',['使用实际App支持的连通操作到自有节点','受控节点断开/恢复后重新验证'],'双方真实收发/状态恢复；保留原网络认证',['controlled_peer_receipt'],condition='源码确认该操作，受控硬件和授权具备')]
 ,LOCAL_STORAGE+' 网络dataset视为敏感凭据，日志不得包含密钥。',['实际Thread特权/角色与邻近设备权限只核对，不绕过','按真实API的网络权限'],
 [need('thread_hardware','Thread radio/合法接口和自有border router/节点','hardware_fixture'),need('thread_dataset','受控测试网络dataset和入网授权','secret_test_input')],
 BASE_FAIL+['缺少Thread HAL/接口/权限、入网失败、邻居/IPv6不可达、恢复后状态残留'],
 hardware=[{'capability':'实际Thread接口、受控边界路由器和节点','required':'required','current_evidence':'UNKNOWN'}],
 notes=['演示App不意味着自动满足生产用途；没有所需Thread设备不能填N/A冒充完成。'])
add('com.google.android.gms','upstream_open_source_service_or_IME',none_account('本地设置可无需账号；实际已启用的账号/推送等服务需要合法测试配置。'),'microg_service',
 [case('microg_settings_selfcheck','实际服务配置与自检读回',['读取真实microG版本、服务配置和自检结果','将失败/未配置条目逐项保存为真实状态'],'设置页与当前安装/服务一致，不把自检失败改成成功',['system_service_readback','official_artifact']),
  case('controlled_service_api','受控客户端调用真实API',['依据当前启用服务选择源码定义的API测试','由同epoch受控客户端发起并读取实际回调/错误'],'服务UID/调用UID/回调一致；仅设置页可打开不够',['controlled_local_peer','system_service_readback']),
  case('enabled_cloud_messaging','已启用推送/账号服务验证',['当实际启用服务属于本次范围时使用自有测试项目/客户端','由受控后端发一条授权测试事件并核对后台接收'],'合法注册、服务端与客户端回执匹配，断网恢复按服务契约完成',['controlled_peer_receipt','vendor_response'],condition='服务实际启用、测试项目/客户端和明确测试消息授权具备')]
 ,LOCAL_STORAGE+' 账号令牌、推送注册凭据不输出；升级前后按正常服务接口核对状态。',
 ['microG实际声明/系统授权与API调用权限','账号/通知/定位按实际配置分支','签名/完整性边界不得更改'],
 [need('microg_client','当前epoch绑定的自有服务API客户端','controlled_local_peer'),need('microg_project','实际启用推送等功能的自有测试服务项目和合法注册','test_service')],
 BASE_FAIL+['服务绑定/自检缺项、合法注册失败、Google服务不可达、后台推送丢失、商业完整性拒绝'],
 notes=['禁止使用签名欺骗、设备/Play完整性伪造或其他绕过商业App有效检查的方案；保持真实失败。'])
add('org.chromium.webview_shell','framework_owned_test_shell',none_account(),'webview_https',
 [case('webview_provider','实际WebView实现与renderer',['读取当前默认WebView provider、版本与APK身份','启动测试shell并绑定实际renderer'],'测试覆盖当前WebView实现，shell versionCode=1不代表实现最新版',['system_service_readback','official_artifact']),
  case('https_dom_chinese','受控HTTPS页面与中文输入',['打开自有可信HTTPS测试页','执行页面声明的DOM/JS nonce回显、中文输入与按钮操作'],'服务器/DOM/IME回读一致，真实脚本执行；拒绝无效TLS证书',['vendor_response','ime_commit']),
  case('web_storage_and_file','网页存储和文件选择',['用自有页面写唯一nonce到LocalStorage/IndexedDB','经正常SAF选择合成文件并在进程重建后回读'],'存储值与所选文件一致，权限范围正确',['scoped_file_roundtrip','storage_readback'])]
 ,LOCAL_STORAGE+' 使用隔离测试origin和合成文件；不清除其他origin或用户会话。',
 ['实际WebView provider/renderer权限','INTERNET','SAF URI授权','相机/麦克风仅另有受控网页媒体分支'],
 [need('https_fixture','自有正常可信证书HTTPS/JS测试origin与独立预期证书错误fixture','test_service'),need('web_files','已知hash合成上传文件')],
 BASE_FAIL+['WebView provider不匹配、renderer崩溃、TLS错误、JS/字体/中文输入失败、网页存储丢失'],
 notes=['本包测试完成不自动说明所有App内嵌WebView兼容，业务App还要自己的回归。'])
add('local.pocket4.fixture','local_owner_built_QA',none_account(),'local_qa_contract',
 [case('fixture_source_contract','解析真实ProbeActivity探针协议',['读取最终已固定的本地源码、manifest和复现清单','列出当前ProbeActivity实际可执行的UI/回显动作与权限'],'协议有可复核源码及与已装APK相同的身份；当前未知项不虚构',['local_source_contract']),
  case('execute_declared_probe','执行源码明确的探针动作',['仅执行上一步实际定义的受控探针并带唯一nonce/动作ID（若协议支持）','通过原sidecar和容器UIAutomator采集真实前后读回'],'输入、动作、结果和helper epoch相互绑定；无该协议则保持UNKNOWN',['local_source_contract','helper_binding']),
  case('probe_negative_and_restart','探针拒绝路径与重启',['对源码已定义的错误输入/身份不符情形验证拒绝','重开后执行新的合法探针'],'拒绝被记录为拒绝，不能复用旧epoch输出',['local_source_contract','helper_binding'])]
 ,LOCAL_STORAGE,['按该实际本地源码的最小manifest/探针能力核对'],
 [need('fixture_contract','最终实际ProbeActivity源码、安装/签名、明确探针协议；本catalog尚未获得完整协议','source_contract')],
 BASE_FAIL+['当前helper/fixture源码未知、旧epoch固定、协议/nonce不符、UI或结果无法关联'],
 notes=['根据Launcher名称猜出的按钮/返回值不作为实际测试；先解析最终源码，之后补具体selector。'])
add('org.droidloom.qa.editorcontract','local_owner_built_QA',none_account(),'local_qa_contract',
 [case('editor_contract','当前编辑器测试契约',['固定最终EditorContractActivity源码、已装APK和当前epoch','识别源码明确的编辑字段/选择区及结果读回接口'],'组件/字段真实存在，helper与安装身份匹配',['local_source_contract','helper_binding']),
  case('unicode_editing','真实中文输入、选择与删除',['通过既有输入链输入“口袋四号 回归测试 123”及标点/emoji','依据实际字段能力移动光标、选择、删除、重新提交并回读UTF-8'],'字符/光标/选择区与预期一致，不能直接修改控件值冒充IME输入',['ime_commit','helper_binding']),
  case('focus_and_restart','焦点、前后台和恢复',['切换可编辑字段/前后台并继续输入','重开后按实际契约验证持久化或明确重置行为'],'焦点和InputConnection正确，状态符合真实源码而非臆测',['helper_binding','storage_readback'])]
 ,LOCAL_STORAGE,['实际EditorContract本地权限','IME/InputConnection能力由系统正常绑定'],
 [need('editor_contract','最终EditorContract源码与当前epoch helper资格清单','source_contract'),need('unicode_fixture','已固定UTF-8输入序列和预期选择/光标变化')],
 BASE_FAIL+['旧epoch helper、InputConnection丢失、中文乱码/重复提交、焦点错误、实际契约未知'],
 notes=['此包不能替代全部商业App文本输入回归。'])
add('org.fcitx.fcitx5.android','upstream_open_source_service_or_IME',none_account(),'local_ime',
 [case('ime_identity','当前IME与中文引擎配置',['核对Fcitx5已装版本、来源与正常系统IME绑定','确认实际可用中文引擎/候选配置'],'实际输入法服务能被当前编辑器正常连接，未启用/缺引擎保留失败',['official_artifact','system_service_readback']),
  case('chinese_candidates','拼音/候选和字符提交',['在当前合格编辑器用实际Fcitx输入已固定中文序列','选择候选、标点、退格、回车并读回UTF-8文本'],'真实IME候选与目标文本正确，不能绕过输入法直接灌字段',['ime_commit','helper_binding']),
  case('cross_app_input','跨App焦点与字典持久化',['在至少一个已资格化业务App中文搜索框重复输入','切前后台/重启后核对允许保存的键盘设置和自有测试词条'],'InputConnection与焦点恢复，测试设置/词条不丢，网络关闭仍能本地输入',['ime_commit','storage_readback'])]
 ,LOCAL_STORAGE+' 不导出真实用户词库/剪贴板；仅使用自有合成词条，正常配置升级保留。',
 ['正常系统IME启用/绑定状态','语言资源的正常文件访问','网络仅实际启用词库/插件需要时核对'],
 [need('ime_fixture','实际已安装中文引擎及版本、合格编辑器与受控输入序列'),need('optional_download_source','若实际需要下载词库/插件，提供官方来源与完整性证据','official_artifact')],
 BASE_FAIL+['IME未绑定/引擎缺失、候选不显示、提交乱码、焦点恢复失败、升级丢配置'],
 notes=['复用既有中文输入与sidecar/UIAutomator；不引入ADB或新控制器。'])

assert set(APPS)==set(by_package),(set(by_package)-set(APPS),set(APPS)-set(by_package))
COMMON={
 'startup_and_current_identity':{'operation':'冷/暖启动并读取实际前台组件、进程、UI树与错误日志；确认不是启动页循环或旧窗口。','required_evidence':['当前epoch/guard前后','包名、UID、versionName/versionCode、base及全部split hash、signer与数据目录','container UIAutomator当前UI树/窗口读回','实际动作receipt与进程退出/ANR/崩溃证据']},
 'session_or_no_login_contract':{'operation':'根据本包真实契约验证正常登录、实际可用访客或本地无需服务账号；三者必须明确，不能用没有看到登录页代替。','required_evidence':['当前认证模式与实际核心路径成功','若无需账号，真实本地组件/数据源证据','认证限制原样记录，不绕过']},
 'permission_behavior':{'operation':'读取完整已装manifest、requested/granted/app-ops/角色前后；验证必需能力与拒绝后的真实行为，最小路径使用现有合法授权。','required_evidence':['当前App身份关联的完整权限快照','实际权限提示/拒绝/错误与用户选择读回','Bili和美团额外授权边界检查']},
 'storage_persistence':{'operation':'正常API/SAF/provider写入自有合成夹具并读回，重启后再次核对；受控只读/不可用存储错误不得破坏已有数据。','required_evidence':['夹具ID/URI/内容hash或字段值','UID与CE/DE身份前后','3次App重启与新qualified runtime中的数据读回']},
 'integrity_and_error_handling':{'operation':'真实完整性、签名、地区、账号和平台权限拒绝均保留；检查错误是否可理解及是否能经合法路径恢复。','required_evidence':['原始错误分类与日志/屏幕/动作绑定','无检测禁用、证书校验禁用、身份伪造或权限扩张','未知结果不得写PASS或自动重放']},
 'long_running':{'operation':'新提议至少连续3600秒；按本包工作负载保持真实功能采样，定期记录前后台、PSS/RSS、FD/线程/任务、网络或本地行为、崩溃/ANR。','required_evidence':['开始/结束时间和不中断的观测序列','同runtime与当前App身份','实际核心读回与资源变化；无法判断稳定时保留UNKNOWN']},
 'app_restart':{'operation':'新提议3次正常App关闭/重开或已授权受控App故障恢复；不清数据，不用改UID/签名替代。','required_evidence':['每次真实旧进程退出/新进程与动作收据','每次核心/状态读回','未决操作先结算，错误路径不省略']},
 'qualified_runtime_restart':{'operation':'由现有原生生命周期控制统一协调真实runtime重启；完成新epoch完整资格后，各包重新固定当前身份并重做核心/持久化。','required_evidence':['真实旧owner退出/新runtime资格和helper新绑定','同一当前安装版本/UID/数据关系','新epoch重测数据；旧epoch PASS不可直接迁移']},
 'fault_recovery':{'operation':'按本包实际依赖执行可控故障：网络App为3次新提议的断网/恢复；离线App为离线连续性/本地provider故障；电话/Thread以受控真实服务故障为准。','required_evidence':['确切故障前状态与故障效果','原始错误/unknown保持不可变','合法恢复后的真实核心读回；缺少硬件或账号留BLOCKED/UNKNOWN']}
}
EVIDENCE={
 'bound_action_and_readback':['qualified runtime/当前App/helper身份','唯一动作ID与实际启动/结束状态','UIAutomator前后XML、可见字段/窗口及实际接口结果','截图只作辅助，不能独立判通过'],
 'current_official_artifact_and_install_identity':['当前发行方或批准官方商店/项目release来源链','完整APK/split集合、版本、ABI/minSdk与所有hash','实际密码学验签以及独立可信发行方签名/轮换链','安装后完整字节/UID/数据目录身份；网页版本不是artifact'],
 'official_artifact':['官方来源/项目构建source-lock','完整安装集与版本/签名','与实际当前运行包匹配'],
 'vendor_response':['同一App动作的真实网络路径/返回字段','实际查询条件与列表/详情对应','不能用其他App、宿主请求或缓存页替代'],
 'authorized_session':['授权账号引用或真实合法访客模式','正常服务认证结果与会话恢复','不包含密码/令牌/证件原文'],
 'controlled_peer_receipt':['明确发送/呼叫/入网授权范围','自有受控对端身份引用','双方真实nonce/时间/状态或媒体回执；未提供对端即不能执行'],
 'controlled_local_peer':['当前epoch的自有接收/调用helper源码/安装/UID','真实调用与返回的动作绑定'],
 'storage_readback':['自有夹具/设置的实际前后值','正常重开及新合格runtime后持久化','UID与CE/DE身份前后'],
 'permission_snapshot':['完整manifest请求集、PM grants、app-ops/角色与UID','实际请求/拒绝时机','前后变化及其授权来源'],
 'media_hardware':['真实设备/provider能力','实际连续帧/音频/编码或双向音频证据','时间进度与操作关联，非静态图片'],
 'media_store_readback':['MediaStore/SAF实际URI及size/metadata','对应已知夹具或真实捕获内容','真实解码/音轨读回'],
 'provider_readback':['受控记录ID和正常provider/UI字段','输入→持久化→重新读取','仅合成数据，不遍历真实个人记录'],
 'scoped_file_roundtrip':['自有目录/URI与当前权限范围','选择/读写/重开后的内容hash','取消、只读和越界拒绝'],
 'notification_delivery':['实际系统调度/通知投递与用户可见状态','触发时刻、后台状态与声音/振动（若适用）','源任务与通知关联'],
 'monotonic_timing':['实际单调时钟参考与App计时读回','完整采样与误差','前后台/重开状态'],
 'system_service_readback':['当前真实系统服务返回及其身份','与UI字段/调用结果一致','不能凭静态设置截图'],
 'hardware_capability':['当前实际声明与可用硬件/driver/HAL','真实能力调用','缺失不能用N/A完成'],
 'delegated_component':['真实intent目标与当前包/UID/provider身份','目标组件实际执行/结果读回','网络证据归属实际执行者'],
 'local_source_contract':['当前最终源码/config/manifest/hash与可执行协议','实际构建/安装身份','未知协议先解析再列selector，不编造函数/按钮'],
 'helper_binding':['helper源码/APK/signature/UID/current epoch','实际受控动作和输出nonce','旧helper或跨epoch拒绝'],
 'ime_commit':['真实IME/target UID/组件/InputConnection绑定','按键/候选/提交序列','目标UTF-8文本、选择区/光标真实回读']
}
out={
 'schema':'pocket4-all-45-app-test-catalog-v1','state':'PLAN_ONLY_ALL_BUSINESS_RESULTS_UNKNOWN',
 'generated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'intent':'给实际观察的45个Launcher包建立可执行前需补齐输入的具体验收计划；不是运行器、实际测试结果或生产就绪证明。',
 'scope':{'observed_launcher_count':45,'catalog_source':'reference/current-native-launcher-catalog.json','catalog_sha256':hashlib.sha256(raw).hexdigest(),
   'observed_utc':catalog['utc'],'fresh_launcher_inventory_complete':False,
   'reason':'原原生列表明确缓存新鲜度未假设；执行和最终清理前必须在同当前epoch重新查询实际完整launcher集合并以digest固定，新增包补入，不能用本表45强制任务完成。',
   'historical_eight_packages':sorted(original_eight),'historical_roster_sha256':policy['historical_roster_sha256'],
   'redroid_current_target':'NONE_RETIRED','redroid_historical_evidence_does_not_qualify_current_native':True},
 'runtime_strategy':{'current_candidate':'Pocket4 DroidLoom built-in Android 17','bridge':'既有sidecar、容器内UI Automator、现有中文输入和合法定位能力','new_ADB_dependency':False,
   'per_run_current_epoch_and_App_scope_required':True,'runtime_identity_distinct_from_versioned_App_identity':True,
   'helper_mismatch_UID_change_or_stale_epoch':'BLOCKED直到正常结算和完整新资格，不静默重绑'},
 'new_proposed_thresholds':copy.deepcopy(policy['proposed_acceptance_thresholds']),
 'applicability_rules':{
   'plan_is_not_PASS':True,'unknown_is_not_not_applicable':True,
   'no_boolean_NA_for_missing_accounts_hardware_targets_or_evidence':True,
   'offline_apps_do_not_require_fabricated_DNS_TLS_PASS':True,
   'offline_completion_instead_requires':'证实实际本地组件/数据源、在已确认离线状态完成真实核心操作、状态持久化和本地故障恢复；已配置在线分支另测。',
   'conditional_case_resolution':'以当前源码/manifest/真实provider/配置/已声明产品范围证据确定是否纳入；解析前保持UNKNOWN，不能靠未提供账号、硬件或失败来判不适用。',
   'unsupported_required_feature':'保留BLOCKED，不能移除Launcher入口、隐藏功能或降低需求来制造全任务完成。',
   'payment_booking_communication_actions':'本计划不新增对外提交授权；受控订单/账号/接收方与明确授权缺失时对应完整业务能力保持UNKNOWN。'},
 'nonnegotiable_boundaries':{'Bili_Accept_historical_cell_only':'p4-bili-m30-cell-20261010','Bili_Accept_authorized_executions_by_this_plan':0,
   'Bili_historical_Accept_not_production_authorization':True,
   'Meituan_proactive_location_grants_forbidden':['android.permission.ACCESS_FINE_LOCATION','android.permission.ACCESS_COARSE_LOCATION'],
   'integrity_security_and_signature_checks_bypass_forbidden':True,
   'source_or_endpoint_spoofing_to_make_tests_pass_forbidden':True,
   'external_messages_or_calls_require_explicit_controlled_peer_authorization':True,
   'no_runtime_UI_install_or_cleanup_actions_performed_by_this_catalog':True},
 'evidence_profiles':EVIDENCE,'common_required_cases':COMMON,
 'cleanup_policy':{'currently_eligible':False,'condition':'全部当前实际Launcher集合和最终framework最新候选实际验收通过；所有失败/unknown/未决安装或动作已结算；保存最终复现材料。',
   'retain_final':['最新可工作的源代码及精确source-lock','实际最终配置与权限/原生生命周期约束','最终framework与所有APK/split身份和来源/签名清单','可复现构建/安装/验收清单','轻量测试与失败结算回执'],
   'retain_until_settlement':['原始失败和unknown证据','尚未验收的新旧版本及必要恢复材料'],
   'eligible_after_all_acceptance':['过期Android framework版本/镜像','过期App APK/split版本','旧构建输出','已结算实验残留','中间版本和重复旧二进制备份'],
   'old_binary_backups_required_forever':False,
   'deletion_scope_rule':'先核对最终在用路径/hash与进程/挂载引用，再列明过期对象的精确路径/hash；不得命中当前最终版本或最终source/config/repro；本文件不执行删除。',
   'synthetic_test_data_restoration':'仅对本次明确归属、已回读结算的合成测试数据按正常API恢复；与旧framework/App版本清理分开记录。'},
 'common_missing_inputs':[need('fresh_current_scope','当前epoch真实完整Launcher查询及所有包/版本/UID/APK集/证书/数据目录','runtime_evidence'),
   need('current_helper','与当前epoch匹配的已真实构建、安装和资格化helper/sidecar UI能力','runtime_evidence'),
   need('final_framework','当前最终framework真实Java/JNI/安装与运行资格；Rust builder通过不足以代替','framework_evidence')],
 'apps':[APPS[x['package']] for x in roster],
 'actual_summary':{'runtime_actions':0,'UI_actions':0,'install_actions':0,'cleanup_actions':0,'apps_tested_by_this_catalog':0,'apps_business_PASS':0,'all_45_business_outcomes':'UNKNOWN_NOT_RUN','production_ready':False,'cleanup_eligible':False}
}
assert len(out['apps'])==45 and {a['package'] for a in out['apps']}==set(by_package)
assert all(a['core_cases'] and not a['production_ready'] and not a['cleanup_eligible'] for a in out['apps'])
assert all(c['actual_result']['state']=='UNKNOWN_NOT_RUN' and not c['actual_result']['evidence_refs'] for a in out['apps'] for c in a['core_cases'])
assert APPS['com.sankuai.meituan.takeoutnew']['permissions']['proactive_grants_authorized_by_this_catalog'] is False
assert APPS['tv.danmaku.bili']['authorization_boundary']['Accept_executions_authorized_by_this_catalog']==0
assert all(a['runtime_targets']['redroid']['current_target'] is None for a in out['apps'])
target=ROOT/'app_test_catalog.json'; target.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'file':str(target),'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
 'apps':len(out['apps']),'core_cases':sum(len(a['core_cases']) for a in out['apps']),'account_or_peer_availability':'all unknown unless separately evidenced','business_PASS':0,
 'network_profiles':{n:sum(a['network']['profile']==n for a in out['apps']) for n in NETWORK}},ensure_ascii=False,indent=2))

