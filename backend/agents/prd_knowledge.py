"""业务域规则库 · 产品文档 AGENT 的 Stage 4 归因表.

每条规则都来自真实源码或 06-business-rules.md，evidence 指向可核对的位置。
AGENT 按需求 ID / 标题关键词命中业务域，把规则注入 PRD 的「业务规则」「异常与边界」章节。
"""

from __future__ import annotations

# 负面清单：06-business-rules.md §7，测试必须覆盖的代码事实缺口
NEGATIVE = {
    "NEG-S01": "发货时 order_item.skuId 为空或 stock 缺失 → 静默跳过，库存不扣仍发货成功",
    "NEG-S02": "退款金额不校验 >0、不校验 <= payAmount，负数/超额退款可被接受",
    "NEG-S05": "编辑商品可直接把 status 写成任意值，绕过上架校验（无图/无SKU/0价直接ON）",
    "NEG-S08": "评价 rating 无代码校验，缺失触发 NPE→500，越界触发 DB CHECK→500",
    "NEG-S09": "地址删除无守卫，可删默认地址/被订单引用的地址",
    "NEG-S10": "分页 size、feedSize、购物车项数无上限",
    "NEG-S12": "支付/发货/售后审核为读-改-写且无行锁，可并发双通过",
    "NEG-S13": "initStock 可写负数 physical，DB CHECK 失败返回 500",
}

DOMAINS: dict[str, dict] = {
    "认证登录": {
        "match_ids": ["V1-FR-001", "V2-FR-001"],
        "match_kw": ["登录", "账密", "验证码", "登出", "退出"],
        "background": "管理端与 C 端使用两套互不通用的身份体系：管理员走账号密码，顾客走手机号验证码。",
        "goal": "让用户安全进入系统，并在失败尝试、令牌时效上具备可预期的行为。",
        "roles": ["管理员", "顾客/会员", "访客"],
        "rules": [
            ("管理端账密登录走 BCrypt 校验；连续失败 5 次锁定 15 分钟", "06-business-rules.md §5"),
            ("C 端手机号+验证码，演示环境固定验证码 123456，无真实短信通道", "06-business-rules.md §5"),
            ("JWT access TTL 900s、refresh TTL 7d；管理端与 C 端令牌不通用", "06-business-rules.md §5"),
        ],
        "flows": ["账密登录成功 → 签发 access/refresh", "验证码登录 → 找得到则登录、找不到则注册", "失败达阈值 → 锁定窗口"],
        "neg": [],
        "ac": [
            "使用正确账密登录返回 200 且拿到 accessToken",
            "密码错误连续 5 次后，第 6 次被锁定 15 分钟",
            "C 端使用固定验证码 123456 可完成登录/注册",
            "用管理端 token 访问 /api/** 被拒绝（令牌不通用）",
        ],
    },
    "RBAC 权限": {
        "match_ids": ["V1-FR-002", "V1-FR-003", "V1-FR-004", "V1-FR-005", "V1-FR-006", "V1-FR-007", "V2-FR-017"],
        "match_kw": ["用户管理", "角色", "菜单", "权限", "部门", "字典", "操作日志", "会员管理"],
        "background": "后台以 RBAC 管理管理员的能力边界，配套组织树与字典等基础数据。",
        "goal": "管理员可被赋予角色、数据范围与菜单/按钮权限，操作全程留痕。",
        "roles": ["超级管理员", "运营管理员", "普通管理员"],
        "rules": [
            ("角色含数据范围字段 dataScope ∈ {ALL, DEPT, SELF}", "RoleSaveReq / 06-business-rules.md §5"),
            ("后端 /admin/** 目前只认证不鉴权；RBAC 主要影响前端菜单与按钮", "06-business-rules.md §5"),
            ("用户支持增删改查、启禁用与重置密码；启禁用作用于登录态", "02-requirements.md V1-FR-002"),
            ("角色含权限绑定（permissionIds），创建/更新角色在同一事务分配菜单权限", "RoleController#create"),
            ("操作日志由 @OpLog 注解记录模块/动作", "RoleController @OpLog"),
        ],
        "flows": ["新建角色 → 勾选权限 → 绑定数据范围", "调整用户角色 → 前端菜单重算", "敏感操作 → 写操作日志"],
        "neg": [],
        "ac": [
            "创建角色时带上 permissionIds，角色的权限树正确回显",
            "把用户置为 DISABLED 后无法用其账号登录",
            "重置密码后旧密码失效",
            "操作角色/用户后在操作日志能查到对应记录",
        ],
    },
    "商品与类目": {
        "match_ids": ["V1-FR-008", "V1-FR-009", "V1-FR-010", "V1-FR-011", "V1-FR-012", "V1-FR-013", "V1-FR-014", "V1-FR-023", "V2-FR-005"],
        "match_kw": ["类目", "品牌", "属性", "商品", "上架", "下架", "文件上传", "工作台", "搜索", "浏览", "导航"],
        "background": "商品采用 SPU + 规格 + SKU 三层模型，后台维护、C 端按可见性规则展示。",
        "goal": "让运营能维护完整的商品档案并控制上架，让 C 端只看到合法可售的商品。",
        "roles": ["商品运营", "顾客"],
        "rules": [
            ("C 端只展示 spu.status=ON 且 deleted=false；SKU 只展示 status=ENABLED", "06-business-rules.md §4"),
            ("上架校验：主图、至少 1 个 SKU、SKU 售价 > 0；库存为 0 允许上架", "06-business-rules.md §4"),
            ("sold_count 在支付成功时按数量增加，取消/关单不回退", "06-business-rules.md §4"),
            ("商品列表/搜索对每个 SPU 额外查 SKU（N+1）", "09-critical-call-chains.md §2"),
        ],
        "flows": ["新建 SPU → 配规格 → 生成 SKU → 填库存 → 上架", "单个/批量下架", "删除草稿"],
        "neg": [
            ("NEG-S05", NEGATIVE["NEG-S05"]),
            ("NEG-S13", NEGATIVE["NEG-S13"]),
        ],
        "ac": [
            "无主图/无 SKU/0 价的商品执行上架被拒绝",
            "库存为 0 但满足其余条件的商品可成功上架",
            "C 端列表不出现 OFF 或已删除的 SPU",
            "支付成功后商品 sold_count 增加对应数量",
        ],
    },
    "库存": {
        "match_ids": ["V1-FR-015", "V1-FR-016", "V1-FR-017", "V2-FR-024"],
        "match_kw": ["库存", "预警", "仓库", "出入库"],
        "background": "库存按 SKU 记账，区分物理库存与锁定库存，兼顾下单锁库存与后台盘点。",
        "goal": "保证 physical ≥ locked ≥ 0 的不变式，并让低库存可被提前发现。",
        "roles": ["仓管", "运营"],
        "rules": [
            ("不变式 physical_stock ≥ locked_stock ≥ 0；available = physical - locked（不落库）", "06-business-rules.md §3"),
            ("两级低库存：lowOnly=available≤阈值；warnOnly=available≤阈值×1.5（含低库存）；同时传 lowOnly 优先；默认阈值 10", "06-business-rules.md §3"),
            ("库存流水类型：INIT / ADJUST / LOCK / UNLOCK / SHIP / SALE_OUT", "06-business-rules.md §3"),
            ("下单/关单用 SELECT … FOR UPDATE；发货/手工调整未检查影响行数", "06-business-rules.md §3"),
        ],
        "flows": ["三态查询（全部/低库存/关注）", "手工调整库存并写 ADJUST 流水", "出入库单生成 SALE_OUT"],
        "neg": [
            ("NEG-S01", NEGATIVE["NEG-S01"]),
            ("NEG-S13", NEGATIVE["NEG-S13"]),
        ],
        "ac": [
            "available 永远等于 physical - locked，且 locked 不会超过 physical",
            "lowOnly 与 warnOnly 同时传入时按 lowOnly 过滤",
            "手工调整负数库存写出库流水，正数写入库流水",
            "低于阈值的 SKU 出现在低库存筛选结果里",
        ],
    },
    "订单交易": {
        "match_ids": ["V1-FR-018", "V1-FR-019", "V2-FR-008", "V2-FR-009", "V2-FR-011", "V2-FR-021", "V2-FR-022"],
        "match_kw": ["订单", "提交", "确认订单", "发货", "收货", "物流", "超时", "导出"],
        "background": "交易是系统核心链路，订单在五态之间流转，任何状态迁移都有严格守卫与库存副作用。",
        "goal": "让用户完成从加购到收货的完整闭环，让运营能发货并处理超时与导出。",
        "roles": ["顾客/会员", "订单运营"],
        "rules": [
            ("状态机：PENDING_PAY → PENDING_SHIP → PENDING_RECEIVE → COMPLETED；PENDING_PAY/CLOSED 经取消或超时关闭", "06-business-rules.md §1"),
            ("OT-01 提交订单：锁库存先于插订单、idempotentKey 必填、整单事务、SELECT FOR UPDATE", "06-business-rules.md §1"),
            ("OT-04 未支付 15 分钟超时关单，LIMIT 100，单条异常只 warn 不阻断", "06-business-rules.md §1"),
            ("OT-05 发货：状态必须待发货、trackingNo 必填，扣 physical+locked，生成 SALE_OUT", "06-business-rules.md §1"),
            ("OT-07 已关闭订单重复取消幂等成功，不二次释放库存", "06-business-rules.md §1"),
        ],
        "flows": [
            "提交订单 → PENDING_PAY（锁库存）",
            "支付成功 → PENDING_SHIP；15 分钟未支付 → CLOSED（解锁）",
            "后台发货 → PENDING_RECEIVE（扣 physical+locked）→ 确认收货 → COMPLETED",
        ],
        "neg": [
            ("NEG-S01", NEGATIVE["NEG-S01"]),
            ("NEG-S12", NEGATIVE["NEG-S12"]),
        ],
        "ac": [
            "提交订单后库存 locked 增加、可购买库存减少，订单为 PENDING_PAY",
            "同一 idempotentKey 重复提交不产生第二笔订单",
            "待付款订单 15 分钟后变为 CLOSED 且库存释放",
            "取消已关闭订单返回成功且库存不再二次释放",
            "发货后订单变为 PENDING_RECEIVE，物流单可查",
        ],
    },
    "售后": {
        "match_ids": ["V1-FR-020", "V1-FR-021", "V2-FR-012"],
        "match_kw": ["售后", "退款", "退货", "换货", "审核"],
        "background": "售后单独立成单，与订单状态耦合；审核通过/驳回决定退款走向。",
        "goal": "让顾客能发起售后、运营能审核，退款过程可追踪。",
        "roles": ["顾客/会员", "客服/运营"],
        "rules": [
            ("状态机 PENDING_AUDIT → REFUNDING → COMPLETED；或 PENDING_AUDIT → REJECTED", "06-business-rules.md §2"),
            ("AS-04 仅订单处于 PENDING_RECEIVE / COMPLETED 可申请售后；AS-05 同订单不可有进行中售后", "06-business-rules.md §2"),
            ("AS-09 驳回必须填处理意见；AS-10 通过时同一事务写 REFUNDING 再写 COMPLETED，REFUNDING 外部不可观测", "06-business-rules.md §2"),
            ("AS-11 三种 type（REFUND/RETURN_REFUND/EXCHANGE）行为一致；EXCHANGE 也走退款，不退货入库", "06-business-rules.md §2"),
        ],
        "flows": ["顾客申请售后 → PENDING_AUDIT", "同意 → REFUNDING（不可观测）→ COMPLETED", "拒绝 → REJECTED（须填意见）"],
        "neg": [
            ("NEG-S02", NEGATIVE["NEG-S02"]),
            ("NEG-S12", NEGATIVE["NEG-S12"]),
        ],
        "ac": [
            "待付款/已关闭订单不能申请售后",
            "同订单存在进行中售后时，再次申请被拒绝",
            "驳回未填处理意见时校验失败",
            "审核通过后售后单直接进入 COMPLETED，不出现可观测的 REFUNDING",
        ],
    },
    "支付": {
        "match_ids": ["V2-FR-010"],
        "match_kw": ["支付", "沙箱", "付款"],
        "background": "演示环境使用沙箱支付，没有真实资金与回调，仅模拟状态推进。",
        "goal": "让用户完成模拟付款，系统据此推进订单状态与销量。",
        "roles": ["顾客/会员"],
        "rules": [
            ("仅待付款、订单归属本人、顾客活跃、沙箱开关开启时可支付", "06-business-rules.md §6"),
            ("写 payment(PAID)、paid_at、sold_count += qty；无真实资金、无回调、无对账", "06-business-rules.md §6"),
        ],
        "flows": ["进入支付页 → 沙箱支付 → 支付成功页"],
        "neg": [("NEG-S12", NEGATIVE["NEG-S12"])],
        "ac": [
            "待付款订单支付后状态变为 PENDING_SHIP 且生成 payment 记录",
            "非本人订单或已支付订单调用支付被拒绝",
            "支付成功后 sold_count 按购买数量增加",
        ],
    },
    "评价": {
        "match_ids": ["V2-FR-015", "V2-FR-025", "EXT-REVIEW-REPLY-001"],
        "match_kw": ["评价", "评论", "回复", "星级"],
        "background": "评价依附已完成订单，C 端展示可见评价，商家可在后台回复。",
        "goal": "让顾客评价已购商品，让商家维护回复，且不影响原始评价。",
        "roles": ["顾客/会员", "商家运营"],
        "rules": [
            ("仅已完成订单可评价，同一订单/商品不可重复评价，评分 1–5", "06-business-rules.md §6"),
            ("商家回复仅写 merchant_reply/replied_at，不改星级/内容/可见性，1–500 字", "06-business-rules.md §6"),
            ("C 端只展示 VISIBLE 评价的回复", "06-business-rules.md §6"),
        ],
        "flows": ["确认收货 → 发表评价", "后台回复评价 → C 端展示回复"],
        "neg": [("NEG-S08", NEGATIVE["NEG-S08"])],
        "ac": [
            "已完成订单可对商品评价一次，重复评价被拒绝",
            "评分应在 1–5 之间，缺失或越界应返回 400 而非 500",
            "商家回复超过 500 字或为空返回 40000",
            "回复后原星级和评价内容不变",
        ],
    },
    "购物车与个人中心": {
        "match_ids": ["V2-FR-007", "V2-FR-013", "V2-FR-014"],
        "match_kw": ["购物车", "收藏", "足迹", "地址", "个人中心", "资料"],
        "background": "C 端个人域管理顾客自己的购物车、收藏、足迹与收货地址。",
        "goal": "让顾客的临时选购与个人资料可持久保存，并在下单时提供有效地址。",
        "roles": ["顾客/会员"],
        "rules": [
            ("购物车按 customer 唯一，条目按 skuId 合并，缺 skuId 拒绝，下单后清空选中项", "06-business-rules.md §6"),
            ("一个顾客多地址、默认地址唯一；下单必须有效 addressId", "06-business-rules.md §6"),
            ("地址 id 为 19 位雪花号，前端必须按字符串处理", "06-business-rules.md §6"),
        ],
        "flows": ["加购 → 勾选 → 结算", "管理地址 → 设为默认", "收藏/浏览足迹增删"],
        "neg": [
            ("NEG-S09", NEGATIVE["NEG-S09"]),
            ("NEG-S10", NEGATIVE["NEG-S10"]),
        ],
        "ac": [
            "同一 SKU 重复加购只产生一条条目并累计数量",
            "默认地址始终唯一，设置新默认会取消旧的",
            "地址 ID 在前端保持字符串不丢精度",
            "下单成功后购物车中选中条目被清空",
        ],
    },
    "首页与运营": {
        "match_ids": ["V2-FR-003", "V2-FR-018", "V2-FR-019", "V2-FR-020", "V1-FR-022", "V2-FR-020"],
        "match_kw": ["首页", "运营位", "品牌", "推荐", "站点", "系统设置", "配置"],
        "background": "首页由站点品牌、运营位与推荐流聚合而成，运营位可按编码配置。",
        "goal": "让运营配置首屏内容，让顾客看到品牌与推荐商品。",
        "roles": ["内容运营", "顾客"],
        "rules": [
            ("首页聚合：品牌 + 运营位 + 推荐流；运营位按 code 取", "09-critical-call-chains.md §1"),
            ("推荐流 toCard 每个 SPU 查一次 SKU，存在 N+1 查询", "09-critical-call-chains.md §1"),
            ("系统配置为 KV，按分类 Tab 管理，敏感值脱敏展示", "02-requirements.md V1-FR-022"),
        ],
        "flows": ["后台配置运营位 → C 端首页按 code 展示", "维护站点品牌"],
        "neg": [("NEG-S10", NEGATIVE["NEG-S10"])],
        "ac": [
            "运营位按 code 配置后 C 端首页对应区域展示",
            "敏感配置在列表/详情中脱敏",
            "未配置运营位时首页不报错",
        ],
    },
    "AI 助手": {
        "match_ids": ["EXT-AI-001"],
        "match_kw": ["AI助手", "智能客服", "对话", "浮窗"],
        "background": "C 端接入独立 Python Agent 服务，提供商品/知识/订单查询对话。",
        "goal": "让顾客通过自然语言快速查商品、问知识、查订单。",
        "roles": ["顾客/会员"],
        "rules": [
            ("接口 POST /api/customer-service/chat 免认证，可选会员 token 透传", "03-api-catalog.md"),
            ("对话走 Agent 子服务（agent_service 8088），不落商城数据库", "01-overview.md / 06-business-rules.md"),
        ],
        "flows": ["浮窗输入问题 → 代理转发 Agent → 流式返回答案"],
        "neg": [],
        "ac": [
            "游客可在浮窗发起对话",
            "带上会员 token 时可查询本人订单",
            "商城库不产生与对话相关的新表",
        ],
    },
    "全站规范": {
        "match_ids": ["V1-FR-024", "V2-FR-016", "V2-FR-026"],
        "match_kw": ["弹窗", "提示", "多端", "双布局", "规范"],
        "background": "这是一类跨页面的交互规范，而不是独立功能，没有专属页面与接口。",
        "goal": "统一全站确认/表单/拒绝/提示的交互，以及 Web/H5 双端布局表现。",
        "roles": ["前端开发", "所有用户"],
        "rules": [
            ("全站统一的确认/表单/拒绝/提示规范（管理端与 C 端各一份）", "02-requirements.md V1-FR-024 / V2-FR-026"),
            ("Web/H5 双布局按视口切换", "02-requirements.md V2-FR-016"),
        ],
        "flows": [],
        "neg": [],
        "ac": [
            "各模块确认/拒绝弹窗文案与按钮顺序一致",
            "同一页面在 Web 与 H5 视口下布局正确",
        ],
        "no_link_reason": "交互规范类需求，没有独立页面与接口，四层链路为空属于正常",
    },
}


def domain_for(req_id: str, title: str):
    """按 ID 精确匹配优先，其次标题关键词。返回 (域标识, 规则字典)。"""
    for key, dom in DOMAINS.items():
        if req_id in dom["match_ids"]:
            return key, dom
    for key, dom in DOMAINS.items():
        if any(kw in title for kw in dom["match_kw"]):
            return key, dom
    return "通用", {
        "background": f"{title} 为系统的一项业务功能。",
        "goal": "按需求描述实现对应能力。",
        "roles": ["系统用户"],
        "rules": [],
        "flows": [],
        "neg": [],
        "ac": [],
    }
