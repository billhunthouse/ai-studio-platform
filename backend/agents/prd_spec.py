"""需求文档规范化的域级素材库.

prd_rewrite.py 用它把「代码证据 + 领域规则」组装成符合《需求文档规范》的 PRD。
所有字段名、错误码、路由均来自真实扫描结果与源码，不得臆造：
  - 表名 / 字段名  ← trace_tables（shang_mall / commerce / identity）
  - 接口路径       ← trace_apis（/api/**、/admin/**）
  - 业务码         ← 源码 GlobalException / ResultCode（40104 锁定、40901 库存不足…）
"""

from __future__ import annotations

# 各域通用：异常七类里必须逐条落地的骨架
COMMON_EXCEPTION_CLASSES = [
    "参数非法", "权限", "状态不允许", "资源不存在", "并发冲突", "依赖失败", "极限值",
]

DOMAIN_SPEC: dict[str, dict] = {
    "认证登录": {
        "problem": "管理端与 C 端各有一套身份体系，登录失败、令牌过期与越权访问缺少统一的可判定行为，导致线上问题只能靠翻日志定位。",
        "value": "登录成功率 ≥ 99%，失败锁定生效后暴力破解尝试在 5 次内被阻断，令牌越权访问 100% 被拒绝。",
        "consequence": "无法登录则全站不可用；锁定策略失效意味着账号可被无限次撞库。",
        "out_of_scope": [
            "真实短信通道（演示环境固定验证码，不接运营商）",
            "第三方 OAuth / 微信授权登录",
            "多因素认证（MFA）与设备指纹",
        ],
        "roles": [
            {"role": "管理员", "entry": "管理端 /login", "operations": ["账号密码登录", "登出"], "dataScope": "identity.admin_user"},
            {"role": "顾客/会员", "entry": "C 端 /login", "operations": ["手机号+验证码登录（不存在则注册）", "登出"], "dataScope": "本人 customer 档案"},
            {"role": "访客", "entry": "C 端浏览页", "operations": ["仅可浏览，触发受保护操作时跳登录"], "dataScope": "无"},
        ],
        "glossary": [
            {"term": "accessToken", "definition": "JWT 访问令牌，TTL 900 秒，放在 Authorization: Bearer 头", "aliases": ["访问令牌", "at"], "forbidden": ["token（歧义）"]},
            {"term": "refreshToken", "definition": "刷新令牌，TTL 7 天，仅用于换取新的 accessToken", "aliases": ["刷新令牌", "rt"], "forbidden": []},
            {"term": "锁定窗口", "definition": "连续失败达阈值后禁止登录的时间段，长度 15 分钟，从达到阈值的那次失败开始计时", "aliases": ["锁定期"], "forbidden": ["封号"]},
            {"term": "令牌不通用", "definition": "管理端令牌无法访问 /api/**，C 端令牌无法访问 /admin/**", "aliases": ["跨端隔离"], "forbidden": []},
        ],
        "nfr": [
            {"category": "安全", "metric": "密码存储算法", "target": "BCrypt(cost=10) 单向哈希，禁止明文/MD5", "measure": "查 identity.admin_user.password 前缀是否为 $2a$"},
            {"category": "安全", "metric": "令牌有效期", "target": "accessToken 900s ± 5s，refreshToken 7d", "measure": "解码 JWT exp 与签发时间差"},
            {"category": "安全", "metric": "越权拦截率", "target": "跨端令牌调用受保护接口 100% 返回 401", "measure": "管理端 token 调 /api/cart"},
            {"category": "性能", "metric": "登录接口 P95", "target": "≤ 300ms（500 并发、思考时间 200ms）", "measure": "k6 混合场景分接口 p95"},
            {"category": "可用性", "metric": "Redis 不可用时的降级", "target": "锁定计数失效但登录主流程可用，记录 ERROR 日志", "measure": "停 Redis 后重试登录"},
        ],
        "invariants": ["同一账号的失败计数与锁定时长必须同源（同一 Redis key）", "锁定窗口内任何密码均不可登录，含正确密码"],
        "deps": [
            {"name": "PostgreSQL 16", "type": "存储", "assumption": "identity.admin_user 表可读写", "fallback": "登录直接失败并返回 500"},
            {"name": "Redis", "type": "缓存", "assumption": "login:fail:<username> 键可写且支持 TTL", "fallback": "跳过锁定校验，记录 WARN，登录继续"},
            {"name": "JWT 签发组件", "type": "内部", "assumption": "全局共享密钥，两端使用同一 secret 但 audience 不同", "fallback": "无降级，签发失败即登录失败"},
        ],
        "fixture": "identity.admin_user 存在 username=admin、status=ENABLED、password 为 BCrypt 密文；Redis 无 login:fail:admin 键",
        "data_assert": "identity.admin_user.last_login_at 被更新为当前时间（±60s）",
        "neg_cases": [
            {"scenario": "请求未携带令牌（Authorization 头缺失）", "feedback": "HTTP 401，code=40102，msg=未登录", "rollback": "无", "retryable": "登录后重试"},
            {"scenario": "令牌已过期（exp 早于当前时间）", "feedback": "HTTP 401，code=40102，msg=令牌已过期", "rollback": "无", "retryable": "用 refreshToken 换新后重试"},
            {"scenario": "密码错误", "feedback": "HTTP 401，code=40101，msg=用户名或密码错误", "rollback": "不写任何数据", "retryable": "是"},
            {"scenario": "连续失败 5 次后第 6 次尝试", "feedback": "HTTP 401，code=40104，msg 含剩余锁定分钟数", "rollback": "不签发令牌", "retryable": "锁定窗口结束后可重试"},
            {"scenario": "请求体缺少 username", "feedback": "HTTP 400，code=40000", "rollback": "不查库", "retryable": "补齐参数后可重试"},
            {"scenario": "用管理端 token 访问 C 端 /api/**", "feedback": "HTTP 401，code=40103", "rollback": "无", "retryable": "换正确端令牌"},
            {"scenario": "账号 status=DISABLED", "feedback": "HTTP 401，code=40105，msg=账号已停用", "rollback": "不签发令牌", "retryable": "否"},
        ],
    },
    "RBAC 权限": {
        "problem": "后台角色、菜单、数据范围靠前端菜单控制，后端只认证不鉴权，越权操作无法从接口层拦截。",
        "value": "角色变更后 1 次刷新内生效；越权调用返回 403 而非静默成功；敏感操作 100% 留痕。",
        "consequence": "任何已登录管理员可直接调用任意 /admin/** 接口，越权改价、删数据无法阻断且难追溯。",
        "out_of_scope": [
            "细粒度字段级权限（列级脱敏由前端做）",
            "组织架构与外部 HR 系统同步",
            "审批流引擎（只保留单级审核）",
        ],
        "roles": [
            {"role": "超级管理员", "entry": "管理端 /system/*", "operations": ["用户/角色/菜单/部门/字典增删改查", "查看操作日志"], "dataScope": "ALL"},
            {"role": "运营管理员", "entry": "管理端 /system/users", "operations": ["查看用户", "重置密码"], "dataScope": "DEPT"},
            {"role": "普通管理员", "entry": "管理端业务页", "operations": ["仅业务操作，不可进系统设置"], "dataScope": "SELF"},
        ],
        "glossary": [
            {"term": "dataScope", "definition": "角色数据范围枚举 ALL/DEPT/SELF，决定该角色可见的数据集合", "aliases": ["数据范围"], "forbidden": ["权限范围"]},
            {"term": "permissionIds", "definition": "角色绑定的菜单/按钮权限 ID 集合，创建角色时在同一事务内写入", "aliases": ["权限点"], "forbidden": []},
            {"term": "操作日志", "definition": "由 @OpLog 注解在 Controller 方法上记录模块、动作、操作人与时间", "aliases": ["审计日志"], "forbidden": []},
        ],
        "nfr": [
            {"category": "安全", "metric": "越权防护", "target": "低权限角色调用未授权接口返回 403；跨端令牌返回 401", "measure": "用运营管理员 token 调 /admin/roles 写接口"},
            {"category": "性能", "metric": "角色权限树加载 P95", "target": "≤ 200ms（权限点 ≤ 500）", "measure": "分接口 k6 p95"},
            {"category": "一致性", "metric": "权限变更生效时延", "target": "≤ 1 次页面刷新（不缓存超过 60s）", "measure": "改角色后立即用该账号访问菜单"},
            {"category": "可维护性", "metric": "敏感操作留痕覆盖", "target": "角色/用户/菜单的写操作 100% 有 @OpLog", "measure": "grep @OpLog 覆盖 Controller 写方法"},
        ],
        "invariants": ["角色删除前必须解除所有用户绑定，否则禁止删除", "内置角色（超级管理员）不可删除、不可改 dataScope"],
        "deps": [
            {"name": "PostgreSQL 16", "type": "存储", "assumption": "role / permission / role_permission 三表可写", "fallback": "权限保存失败整体回滚"},
            {"name": "JWT 载荷", "type": "内部", "assumption": "roles/permissions 编入令牌，改权限需重新登录生效", "fallback": "旧令牌沿用旧权限直到过期"},
        ],
        "fixture": "identity.admin_user 中存在 role=运营管理员 的账号；permission 表存在菜单权限记录；调用方持有超级管理员 token",
        "data_assert": "identity.role_permission 新增对应 (role_id, permission_id) 行；identity.op_log 新增一条 op_type=CREATE/UPDATE 记录",
        "neg_cases": [
            {"scenario": "角色名重复", "feedback": "HTTP 409，code=40902，msg=角色编码已存在", "rollback": "不写库", "retryable": "换编码后重试"},
            {"scenario": "删除仍被用户绑定的角色", "feedback": "HTTP 409，code=40903，msg=角色下仍有用户", "rollback": "不删除", "retryable": "解绑后重试"},
            {"scenario": "普通管理员调用 /admin/roles 写接口", "feedback": "HTTP 403，code=40300", "rollback": "无", "retryable": "否"},
            {"scenario": "permissionIds 含不存在的权限 ID", "feedback": "HTTP 400，code=40001，msg=权限不存在", "rollback": "整体回滚，不产生半绑定数据", "retryable": "修正后重试"},
        ],
    },
    "商品与类目": {
        "problem": "商品采用 SPU+SKU 三层模型，上下架与可见性规则分散在多个接口，C 端可能看到不该展示的商品。",
        "value": "C 端列表只出现 status=ON 且 deleted=false 的 SPU；上架校验拦截无图/无 SKU/0 价商品，异常上架 0 例。",
        "consequence": "脏商品上架会直接产生无法履约的订单，退款与客诉成本上升。",
        "out_of_scope": [
            "多规格组合的批量导入（Excel 批量导入不做）",
            "商品审核流（运营上架即生效）",
            "跨境多币种定价",
        ],
        "roles": [
            {"role": "商品运营", "entry": "管理端 /products、/categories", "operations": ["类目/品牌/属性维护", "SPU 与 SKU 编辑", "上下架"], "dataScope": "全部商品"},
            {"role": "顾客", "entry": "C 端 /、/category、/product/:spuId、/search", "operations": ["浏览、搜索、看详情"], "dataScope": "仅 ON 商品"},
        ],
        "glossary": [
            {"term": "SPU", "definition": "标准产品单元，对应 commerce.spu，一个 SPU 下挂多个 SKU", "aliases": ["商品", "货品"], "forbidden": ["产品（与需求条目混淆）"]},
            {"term": "SKU", "definition": "最小库存单元，对应 commerce.sku，含独立价格与条码", "aliases": ["规格", "单品"], "forbidden": []},
            {"term": "上架校验", "definition": "status 置 ON 前必须满足：主图非空、至少 1 个 SKU、SKU 售价 > 0；库存为 0 允许上架", "aliases": ["上架规则"], "forbidden": []},
        ],
        "nfr": [
            {"category": "性能", "metric": "商品列表接口 P95", "target": "≤ 200ms（单页 20 条、500 并发）", "measure": "k6 /api/products?page=1&size=20"},
            {"category": "性能", "metric": "列表接口 SQL 次数", "target": "≤ 3 次/请求（现状 22 次，N+1 待修）", "measure": "pg_stat_statements calls 增量 ÷ 请求数"},
            {"category": "容量", "metric": "SPU 规模", "target": "支持 10 万 SPU、50 万 SKU 的分页查询", "measure": "造数后压测 P95"},
            {"category": "安全", "metric": "未授权访问", "target": "C 端接口不可返回 status=OFF 的商品，越权返回 404 而非 403（不泄露存在性）", "measure": "直接请求已下架 spuId"},
        ],
        "invariants": ["spu.deleted=false 且 status=ON 才可被 C 端检索", "sku.price > 0 才允许上架", "spu.sold_count 只在支付成功时递增，取消不回退"],
        "deps": [
            {"name": "PostgreSQL 16", "type": "存储", "assumption": "commerce.spu/sku/category 可读写", "fallback": "列表返回空并记录 ERROR"},
            {"name": "对象存储 / 本地文件", "type": "存储", "assumption": "主图可上传并返回可访问 URL", "fallback": "上传失败阻断上架"},
        ],
        "fixture": "commerce.spu 存在 status=ON、deleted=false 的 SPU，其下 ≥ 1 个 status=ENABLED 的 SKU；commerce.category 存在 level=1 的根类目",
        "data_assert": "commerce.spu.status 变更为 ON/OFF；commerce.category.deleted 被置 true（软删）",
        "neg_cases": [
            {"scenario": "上架时无主图", "feedback": "HTTP 400，code=40010，msg=请先上传主图", "rollback": "status 保持原值", "retryable": "补图后重试"},
            {"scenario": "上架时无 SKU", "feedback": "HTTP 400，code=40011，msg=至少需要一个 SKU", "rollback": "status 保持原值", "retryable": "补 SKU 后重试"},
            {"scenario": "SKU 售价为 0", "feedback": "HTTP 400，code=40012，msg=SKU 价格必须大于 0", "rollback": "status 保持原值", "retryable": "改价后重试"},
            {"scenario": "把 spu.status 直接写成非法值（绕过校验）", "feedback": "期望 HTTP 400，实际可能 200（NEG-S05 未修）", "rollback": "无法保证", "retryable": "—"},
            {"scenario": "分页 size=100000", "feedback": "期望 HTTP 400 或被截断到上限，实际全量返回（NEG-S10）", "rollback": "无写入", "retryable": "改为合法 size"},
        ],
    },
    "库存": {
        "problem": "库存分物理库存与锁定库存两档，扣减与释放分散在下单、支付、关单三处，缺少统一不变式约束。",
        "value": "任何时刻 physical_stock ≥ locked_stock ≥ 0；并发下单不超卖，超卖率 0。",
        "consequence": "超卖会产生无法发货的订单；负库存使后续补货判断全部失真。",
        "out_of_scope": [
            "多仓调拨与仓间移库（仅保留出入库单记录）",
            "库存预测与自动补货",
            "批次/效期管理",
        ],
        "roles": [
            {"role": "仓库管理员", "entry": "管理端 /stocks、/warehouses", "operations": ["初始化库存", "调阈值", "出入库"], "dataScope": "所辖仓库"},
            {"role": "顾客", "entry": "C 端商品详情/下单", "operations": ["间接消耗库存"], "dataScope": "不可见具体库存数"},
        ],
        "glossary": [
            {"term": "physical_stock", "definition": "物理库存总量，对应 commerce.stock.physical_stock", "aliases": ["总库存"], "forbidden": ["库存（歧义）"]},
            {"term": "locked_stock", "definition": "已下单未支付占用的库存，支付成功转实扣，关单释放", "aliases": ["锁定库存", "占用库存"], "forbidden": ["冻结库存"]},
            {"term": "available", "definition": "可售库存 = physical_stock − locked_stock，恒 ≥ 0", "aliases": ["可售库存"], "forbidden": []},
            {"term": "预警阈值", "definition": "commerce.stock.low_threshold，可售低于该值进入预警", "aliases": ["安全库存"], "forbidden": []},
        ],
        "nfr": [
            {"category": "一致性与并发", "metric": "超卖率", "target": "0（500 并发抢同 SKU）", "measure": "并发下单后校验 physical_stock ≥ locked_stock ≥ 0"},
            {"category": "性能", "metric": "库存扣减耗时", "target": "单次 ≤ 50ms（P95）", "measure": "下单链路分段计时"},
            {"category": "可靠性", "metric": "乐观锁冲突重试", "target": "version 冲突时最多重试 3 次后返回 409", "measure": "构造并发更新 stock.version"},
        ],
        "invariants": [
            "INV-01 physical_stock ≥ locked_stock ≥ 0",
            "INV-02 available = physical_stock − locked_stock ≥ 0",
            "INV-03 每次扣减写 stock_log(change_qty, type, reason, operator_id)",
        ],
        "deps": [
            {"name": "PostgreSQL 16", "type": "存储", "assumption": "commerce.stock 支持行锁/乐观锁（version 列）", "fallback": "无降级，扣减失败即下单失败"},
            {"name": "定时任务", "type": "内部", "assumption": "每分钟扫描超时未支付订单释放库存", "fallback": "锁定库存堆积，需人工释放"},
        ],
        "fixture": "commerce.stock 存在 sku_id=1、physical_stock=100、locked_stock=0、version=1 的行",
        "data_assert": "下单后 commerce.stock.locked_stock +N；支付后 physical_stock −N 且 locked_stock −N；commerce.stock_log 新增一条 change_qty=-N",
        "neg_cases": [
            {"scenario": "可售库存不足", "feedback": "HTTP 409，code=40901，msg=库存不足", "rollback": "不锁库存、不建单", "retryable": "补货后重试"},
            {"scenario": "并发抢最后 1 件", "feedback": "仅 1 个请求成功，其余 code=40901", "rollback": "失败方无写入", "retryable": "否"},
            {"scenario": "initStock 传负数 physical", "feedback": "期望 HTTP 400，实际可能 500（NEG-S13）", "rollback": "DB CHECK 失败回滚", "retryable": "修正后重试"},
            {"scenario": "version 冲突", "feedback": "HTTP 409，code=40904，msg=库存已被修改请重试", "rollback": "本次扣减回滚", "retryable": "是（≤3 次）"},
        ],
    },
    "订单交易": {
        "problem": "订单状态机跨下单、支付、发货、收货、关单五步，状态迁移与超时关单依赖定时任务，缺少非法迁移的显式拒绝。",
        "value": "订单状态迁移全部走白名单；超时未支付 15 分钟内自动关单并释放库存；重复提交被幂等键拦截。",
        "consequence": "状态可被任意改写会导致已关闭订单再次发货、重复扣库存。",
        "out_of_scope": [
            "拆单与合单",
            "发票开具",
            "物流轨迹实时对接（仅存运单号与静态轨迹）",
        ],
        "roles": [
            {"role": "顾客", "entry": "C 端 /cart → /checkout → /orders", "operations": ["下单", "取消", "确认收货", "查看订单"], "dataScope": "本人订单"},
            {"role": "运营管理员", "entry": "管理端 /orders", "operations": ["查看", "发货", "关单备注"], "dataScope": "全部订单"},
        ],
        "glossary": [
            {"term": "订单状态机", "definition": "PENDING_PAY → PENDING_SHIP → SHIPPED → COMPLETED，任一状态可迁 CLOSED（除 COMPLETED）", "aliases": ["订单流转"], "forbidden": ["订单状态（泛指）"]},
            {"term": "幂等键", "definition": "commerce.order.idempotent_key，同一用户同键只生成一单", "aliases": ["幂等标识"], "forbidden": []},
            {"term": "超时关单", "definition": "PENDING_PAY 超过 15 分钟由定时任务置 CLOSED 并 release 锁库存", "aliases": ["自动关单"], "forbidden": ["过期订单"]},
        ],
        "nfr": [
            {"category": "性能", "metric": "下单接口 P95", "target": "≤ 500ms（500 并发、库存充足）", "measure": "k6 POST /api/orders p95"},
            {"category": "一致性", "metric": "重复下单拦截", "target": "相同 idempotent_key 第二次请求返回同一 orderNo，不新建订单", "measure": "连续两次相同键下单"},
            {"category": "可靠性", "metric": "超时关单时延", "target": "超时后 ≤ 60s 完成关单与库存释放", "measure": "构造 16 分钟前订单，等 1 分钟查库"},
            {"category": "安全", "metric": "越权访问他人订单", "target": "返回 403/404，不返回订单详情", "measure": "A 用户 token 请求 B 用户 orderId"},
        ],
        "invariants": [
            "INV-04 订单金额 = Σ(order_item.subtotal) + freight − 优惠，误差 ≤ 0.01",
            "INV-05 只有 PENDING_SHIP 可发货；非该状态发货必须拒绝且不写 shipment",
            "INV-06 CLOSED 订单不可再支付",
        ],
        "deps": [
            {"name": "PostgreSQL 16", "type": "存储", "assumption": "commerce.order/order_item/order_event_log 同事务写入", "fallback": "下单整体回滚"},
            {"name": "定时任务 CommerceJobs", "type": "内部", "assumption": "每分钟扫描超时订单，单批上限 100", "fallback": "订单滞留 PENDING_PAY，库存不释放"},
        ],
        "fixture": "顾客已登录；购物车含 ≥1 个可售 SKU；commerce.stock 可售充足；地址已存在默认地址",
        "data_assert": "commerce.order 新增 1 行（status=PENDING_PAY、pay_amount 与 items 合计一致）；commerce.order_item 数量与购物车一致；order_event_log 写 CREATE 事件",
        "neg_cases": [
            {"scenario": "购物车为空下单", "feedback": "HTTP 400，code=40020，msg=购物车为空", "rollback": "不建单", "retryable": "加购后重试"},
            {"scenario": "重复提交同一 idempotent_key", "feedback": "HTTP 200，返回已存在 orderNo", "rollback": "不新建订单", "retryable": "—"},
            {"scenario": "对 SHIPPED 订单再发货", "feedback": "HTTP 409，code=40905，msg=当前状态不允许发货", "rollback": "不写 shipment", "retryable": "否"},
            {"scenario": "支付与关单并发", "feedback": "以行锁/状态 CAS 保证只有一方成功（NEG-S12 未修前可能双成功）", "rollback": "失败方回滚", "retryable": "重新查询状态"},
            {"scenario": "请求他人 orderId", "feedback": "HTTP 403，code=40301", "rollback": "无", "retryable": "否"},
        ],
    },
    "售后": {
        "problem": "售后单与订单状态、退款金额之间缺少强校验，审核与退款可绕过金额边界。",
        "value": "退款金额 0 < refund_amount ≤ order.pay_amount；售后单状态迁移受状态机约束；审核动作可追溯。",
        "consequence": "负数或超额退款直接造成资金损失，且事后难以从数据上判定责任。",
        "out_of_scope": [
            "换货与维修流程（仅退款/退货退款）",
            "与原支付渠道的自动退款对接（演示环境为模拟退款）",
            "仲裁与平台介入",
        ],
        "roles": [
            {"role": "顾客", "entry": "C 端 /orders/:id/after-sale", "operations": ["发起售后", "查看进度"], "dataScope": "本人售后单"},
            {"role": "客服管理员", "entry": "管理端 /after-sales", "operations": ["审核通过/驳回", "发起退款"], "dataScope": "全部售后单"},
        ],
        "glossary": [
            {"term": "售后单", "definition": "commerce.after_sale，一条订单可多次发起但同订单同时只允许一个进行中售后", "aliases": ["工单"], "forbidden": []},
            {"term": "退款金额", "definition": "commerce.after_sale.refund_amount，必须 > 0 且 ≤ order.pay_amount", "aliases": ["退款额"], "forbidden": ["赔偿金"]},
        ],
        "nfr": [
            {"category": "安全/资金", "metric": "退款金额校验", "target": "0 < refund_amount ≤ pay_amount，越界返回 400", "measure": "构造 refund_amount=-1 / pay_amount+1"},
            {"category": "性能", "metric": "售后列表 P95", "target": "≤ 200ms", "measure": "分接口 k6 p95"},
            {"category": "可追溯", "metric": "审核留痕", "target": "audit_remark、审核人、时间 100% 落库", "measure": "审核后查 after_sale 行"},
        ],
        "invariants": ["INV-07 0 < after_sale.refund_amount ≤ order.pay_amount", "INV-08 同一订单同时只允许 1 个 status 非终态的售后单"],
        "deps": [
            {"name": "PostgreSQL 16", "type": "存储", "assumption": "commerce.after_sale 可写", "fallback": "售后申请失败并提示"},
            {"name": "支付模块", "type": "内部", "assumption": "退款走模拟通道，返回成功即视为退款完成", "fallback": "退款失败置 REFUND_FAILED，可重试"},
        ],
        "fixture": "commerce.order 存在 status=COMPLETED、pay_amount=199.00 的订单，customer_id 与登录用户一致",
        "data_assert": "commerce.after_sale 新增 1 行（status=PENDING_AUDIT、refund_amount ≤ pay_amount）；审核后 status 变更且 audit_remark 非空",
        "neg_cases": [
            {"scenario": "refund_amount = -1", "feedback": "期望 HTTP 400，实际可能被接受（NEG-S02）", "rollback": "无法保证", "retryable": "—"},
            {"scenario": "refund_amount > pay_amount", "feedback": "期望 HTTP 400，实际可能被接受（NEG-S02）", "rollback": "无法保证", "retryable": "—"},
            {"scenario": "对未完成订单发起售后", "feedback": "HTTP 409，code=40906，msg=订单状态不支持售后", "rollback": "不建售后单", "retryable": "订单完成后再试"},
            {"scenario": "同一订单并发两次审核", "feedback": "只有一次成功，另一次 409（NEG-S12 未修前可能双成功）", "rollback": "失败方回滚", "retryable": "刷新后重试"},
        ],
    },
    "支付": {
        "problem": "支付回调与订单状态之间的联动缺少幂等与金额一致性校验，重复回调可能重复置为已支付。",
        "value": "同一笔支付重复回调只生效一次；支付金额与订单 pay_amount 不一致时拒绝置为已支付。",
        "consequence": "重复回调会把已关闭订单重新置为已支付，造成资损与超卖。",
        "out_of_scope": [
            "真实第三方支付对接（微信/支付宝沙箱）",
            "分账与结算",
            "退款到账时效保障",
        ],
        "roles": [
            {"role": "顾客", "entry": "C 端 /checkout/pay", "operations": ["发起支付", "查看支付结果"], "dataScope": "本人支付单"},
            {"role": "运营管理员", "entry": "管理端 /payments", "operations": ["查看支付流水"], "dataScope": "全部支付单"},
        ],
        "glossary": [
            {"term": "支付单", "definition": "commerce.payment，一笔订单可有多条支付尝试，仅一条 status=SUCCESS", "aliases": ["流水"], "forbidden": []},
            {"term": "回调幂等", "definition": "相同 trade_no 的重复回调不得改变最终状态", "aliases": ["回调去重"], "forbidden": []},
        ],
        "nfr": [
            {"category": "一致性", "metric": "回调幂等", "target": "重复回调 10 次，payment 仍只有 1 条 SUCCESS，订单只置一次已支付", "measure": "重复投递同一回调"},
            {"category": "性能", "metric": "支付接口 P95", "target": "≤ 500ms", "measure": "分接口 k6 p95"},
            {"category": "安全", "metric": "金额一致性", "target": "payment.amount = order.pay_amount，不等则拒绝", "measure": "构造金额不一致回调"},
        ],
        "invariants": ["INV-09 每笔订单最多 1 条 payment.status=SUCCESS", "INV-10 payment.amount = order.pay_amount"],
        "deps": [
            {"name": "支付通道（模拟）", "type": "外部", "assumption": "本地模拟支付返回 success 并回调", "fallback": "支付失败置 FAILED，可重新支付"},
            {"name": "RabbitMQ", "type": "消息", "assumption": "支付成功事件投递 MQ 用于异步处理", "fallback": "MQ 不可用时改为同步处理并记录 WARN"},
        ],
        "fixture": "commerce.order 存在 status=PENDING_PAY、pay_amount=199.00 的订单；对应 payment 无 SUCCESS 记录",
        "data_assert": "commerce.payment 新增/更新为 status=SUCCESS 且 trade_no 非空；commerce.order.status 变为 PENDING_SHIP 且 paid_at 非空",
        "neg_cases": [
            {"scenario": "重复回调同一 trade_no", "feedback": "HTTP 200 但状态不变", "rollback": "无副作用", "retryable": "—"},
            {"scenario": "回调金额与订单不一致", "feedback": "HTTP 400，code=40030，msg=支付金额不一致", "rollback": "不置已支付", "retryable": "否"},
            {"scenario": "对 CLOSED 订单支付", "feedback": "HTTP 409，code=40907，msg=订单已关闭", "rollback": "不写 payment", "retryable": "否"},
        ],
    },
    "评价": {
        "problem": "评价接口缺少 rating 取值校验，缺失字段触发 NPE，越界触发数据库 CHECK 失败，两者都表现为 500。",
        "value": "rating ∈ {1..5} 且必填；非本订单用户不可评价；同一 order_item 只可评价一次。",
        "consequence": "500 错误暴露内部堆栈，且前端无法给出可理解的提示；重复评价会污染评分。",
        "out_of_scope": ["图片鉴黄", "评价审核流", "商家回复的多轮对话"],
        "roles": [
            {"role": "顾客", "entry": "C 端 /orders/:id/review", "operations": ["提交评价", "查看我的评价"], "dataScope": "本人订单"},
            {"role": "运营管理员", "entry": "管理端 /reviews", "operations": ["查看", "回复", "隐藏违规评价"], "dataScope": "全部评价"},
        ],
        "glossary": [
            {"term": "rating", "definition": "commerce.review.rating，整数 1..5，必填", "aliases": ["评分"], "forbidden": ["星级（前端文案）"]},
            {"term": "评价归属", "definition": "评价必须绑定 order_item_id，且该 order_item 属于当前用户", "aliases": ["评价来源"], "forbidden": []},
        ],
        "nfr": [
            {"category": "健壮性", "metric": "非法 rating 处理", "target": "缺失/0/6/非数字 → HTTP 400，禁止 500", "measure": "构造 rating=null / 0 / 6"},
            {"category": "性能", "metric": "评价列表 P95", "target": "≤ 200ms", "measure": "分接口 k6 p95"},
        ],
        "invariants": ["INV-11 1 ≤ review.rating ≤ 5", "INV-12 每个 order_item 最多 1 条 review"],
        "deps": [{"name": "PostgreSQL 16", "type": "存储", "assumption": "commerce.review 有 rating CHECK 约束", "fallback": "约束失败返回 400 而非 500"}],
        "fixture": "commerce.order_item 存在属于当前用户、status=COMPLETED 且未评价的行",
        "data_assert": "commerce.review 新增 1 行（rating ∈ 1..5、order_item_id 唯一）",
        "neg_cases": [
            {"scenario": "rating 缺失", "feedback": "期望 HTTP 400，实际 NPE→500（NEG-S08）", "rollback": "无写入", "retryable": "补齐后重试"},
            {"scenario": "rating=6", "feedback": "期望 HTTP 400，实际 DB CHECK→500（NEG-S08）", "rollback": "回滚", "retryable": "改合法值"},
            {"scenario": "评价他人订单", "feedback": "HTTP 403，code=40302", "rollback": "不写入", "retryable": "否"},
            {"scenario": "重复评价同一 order_item", "feedback": "HTTP 409，code=40908，msg=该订单已评价", "rollback": "不写入", "retryable": "否"},
        ],
    },
    "购物车与个人中心": {
        "problem": "购物车、收藏、地址、浏览历史分散在多个接口，数据范围只按 customer_id 过滤，缺少条数与并发上限。",
        "value": "购物车项数 ≤ 100 且单项数量 ≤ 999；地址删除不破坏被订单引用的快照；所有接口只能操作本人数据。",
        "consequence": "无上限的购物车可被脚本刷爆；误删默认地址导致下单失败。",
        "out_of_scope": ["跨端购物车同步冲突合并", "地址智能识别（仅手工填写）", "收藏夹分组"],
        "roles": [
            {"role": "顾客/会员", "entry": "C 端 /cart、/user/*", "operations": ["加购/改量/删除", "收藏", "地址增删改", "看浏览历史"], "dataScope": "本人数据"},
        ],
        "glossary": [
            {"term": "购物车项", "definition": "commerce.cart_item，同一 cart 下 sku_id 唯一，数量 1..999", "aliases": ["购物车条目"], "forbidden": []},
            {"term": "默认地址", "definition": "commerce.address.is_default=true，同一用户最多 1 条", "aliases": ["常用地址"], "forbidden": []},
            {"term": "浏览历史", "definition": "commerce.browse_history，按 customer_id+spu_id 覆盖更新 last_at", "aliases": ["足迹"], "forbidden": []},
        ],
        "nfr": [
            {"category": "性能", "metric": "购物车接口 P95", "target": "≤ 200ms（≤100 项）", "measure": "分接口 k6 p95"},
            {"category": "安全", "metric": "数据隔离", "target": "操作他人 cart_item/address 返回 403/404", "measure": "用 A 用户 token 操作 B 用户资源"},
            {"category": "健壮性", "metric": "上限保护", "target": "购物车项 > 100 或数量 > 999 返回 400（NEG-S10 待修）", "measure": "循环加购 101 项"},
        ],
        "invariants": ["INV-13 同一用户同 SKU 在购物车只有 1 行", "INV-14 同一用户最多 1 条 is_default 地址"],
        "deps": [{"name": "PostgreSQL 16", "type": "存储", "assumption": "commerce.cart/cart_item/address 可写", "fallback": "操作失败返回 500 并提示重试"}],
        "fixture": "顾客已登录；commerce.cart 存在其购物车；commerce.address 存在 1 条默认地址",
        "data_assert": "commerce.cart_item 新增/更新 quantity；commerce.address.is_default 唯一性保持",
        "neg_cases": [
            {"scenario": "加购数量 0 或负数", "feedback": "HTTP 400，code=40040，msg=数量必须大于 0", "rollback": "不写入", "retryable": "改合法值"},
            {"scenario": "操作他人 cart_item", "feedback": "HTTP 403，code=40303", "rollback": "无", "retryable": "否"},
            {"scenario": "删除被订单引用的地址", "feedback": "期望 HTTP 409，实际可能直接删除（NEG-S09，订单用快照不受影响）", "rollback": "无法保证", "retryable": "—"},
            {"scenario": "购物车加到 101 项", "feedback": "期望 HTTP 400 上限提示，实际允许（NEG-S10）", "rollback": "无", "retryable": "删除后用"},
        ],
    },
    "首页与运营": {
        "problem": "首页坑位、品牌信息等运营内容由配置驱动，缺少有效期与上下线校验，可能展示过期或空坑位。",
        "value": "坑位仅在 valid_from..valid_to 内展示；无有效商品时整块降级隐藏，不留空壳。",
        "consequence": "过期活动仍展示会造成客诉与资损（价格与活动不一致）。",
        "out_of_scope": ["A/B 实验与千人千面推荐", "活动优惠券叠加计算引擎", "内容审核"],
        "roles": [
            {"role": "运营管理员", "entry": "管理端 /home/slots", "operations": ["配置坑位", "上下线", "排序"], "dataScope": "全站"},
            {"role": "顾客/访客", "entry": "C 端 /", "operations": ["浏览首页"], "dataScope": "仅有效坑位"},
        ],
        "glossary": [
            {"term": "坑位", "definition": "commerce.home_slot，首页可配置区块，含 code 唯一标识与有效期", "aliases": ["楼层", "区块"], "forbidden": []},
            {"term": "坑位项", "definition": "commerce.home_slot_item，坑位内商品/图文，按 sort 排序", "aliases": ["楼层商品"], "forbidden": []},
        ],
        "nfr": [
            {"category": "性能", "metric": "首页聚合接口 P95", "target": "≤ 300ms", "measure": "k6 GET /api/home"},
            {"category": "正确性", "metric": "有效期过滤", "target": "过期/未开始坑位不返回（100%）", "measure": "造过期坑位后请求首页"},
        ],
        "invariants": ["INV-15 valid_from ≤ valid_to", "INV-16 坑位项引用的 SPU 必须 status=ON 才展示"],
        "deps": [{"name": "PostgreSQL 16", "type": "存储", "assumption": "commerce.home_slot/home_slot_item 可写", "fallback": "首页降级为默认推荐"}],
        "fixture": "commerce.home_slot 存在 status=ON 且在有效期内的坑位，坑位内含 ≥1 个 ON 商品",
        "data_assert": "commerce.home_slot.valid_from/valid_to 按提交值写入；排序 sort 连续",
        "neg_cases": [
            {"scenario": "valid_from > valid_to", "feedback": "HTTP 400，code=40050，msg=开始时间不能晚于结束时间", "rollback": "不写入", "retryable": "修正后重试"},
            {"scenario": "坑位项引用已下架商品", "feedback": "首页不展示该项（过滤而非报错）", "rollback": "无", "retryable": "—"},
        ],
    },
    "AI 助手": {
        "problem": "客服 AI 依赖外部 LLM 与知识库检索，缺少不可用时的降级与答案可追溯要求。",
        "value": "LLM 不可用时降级为 FAQ 检索并在 3 秒内响应；答案命中知识库时给出出处。",
        "consequence": "LLM 超时会让对话接口长时间挂起，前端表现为一直转圈。",
        "out_of_scope": ["多轮复杂业务办理（仅咨询与查询）", "人工坐席转接", "语音交互"],
        "roles": [
            {"role": "顾客", "entry": "C 端悬浮客服", "operations": ["提问", "查看答案出处"], "dataScope": "本人会话"},
            {"role": "客服管理员", "entry": "管理端 /kb", "operations": ["维护知识库文档"], "dataScope": "全部文档"},
        ],
        "glossary": [
            {"term": "知识库检索", "definition": "按分词命中 kbChunks 并按得分排序返回 top-k 片段", "aliases": ["RAG 召回"], "forbidden": []},
            {"term": "降级", "definition": "LLM 不可用时仅返回检索片段原文，不再生成", "aliases": ["兜底"], "forbidden": []},
        ],
        "nfr": [
            {"category": "性能", "metric": "对话接口 P95", "target": "≤ 3s；LLM 超时阈值 8s 后降级", "measure": "分接口 k6 p95"},
            {"category": "可用性", "metric": "LLM 不可用降级", "target": "100% 请求在 3s 内返回检索结果", "measure": "停 LLM 服务后请求"},
            {"category": "可解释", "metric": "答案出处", "target": "命中知识库时返回 docId 与片段", "measure": "检查响应 sources 字段"},
        ],
        "invariants": ["单次回答的引用片段必须来自当前项目知识库", "降级路径不得返回空字符串"],
        "deps": [
            {"name": "LLM 服务（8010）", "type": "外部", "assumption": "OpenAI 兼容接口可用", "fallback": "降级为知识库检索"},
            {"name": "知识库索引", "type": "内部", "assumption": "kbChunks 已索引且可检索", "fallback": "返回默认 FAQ 文案"},
        ],
        "fixture": "知识库 KB-1 已索引业务规则文档；LLM 服务可用",
        "data_assert": "会话消息落库（conversations 集合新增 1 条 assistant 消息）",
        "neg_cases": [
            {"scenario": "LLM 超时", "feedback": "8s 后降级返回检索片段，HTTP 200", "rollback": "无", "retryable": "是"},
            {"scenario": "知识库无命中", "feedback": "HTTP 200，返回兜底文案并标记 degraded=true", "rollback": "无", "retryable": "是"},
            {"scenario": "空问题", "feedback": "HTTP 400，code=40060", "rollback": "不落库", "retryable": "补充问题"},
        ],
    },
    "全站规范": {
        "problem": "交互规范类要求（提示、弹窗、空态）散落在各页面实现，缺少统一约束，导致同类场景表现不一致。",
        "value": "同类交互（成功/失败/确认/空态）在全部页面表现一致，可被视觉与交互走查逐项核对。",
        "consequence": "用户在不同页面遇到不同的反馈方式，学习成本上升，问题难以归因。",
        "out_of_scope": ["视觉设计稿本身（Figma 交付物）", "品牌字体与配色规范", "国际化多语言文案"],
        "roles": [
            {"role": "前端开发", "entry": "全部页面", "operations": ["按规范实现提示与弹窗"], "dataScope": "—"},
            {"role": "测试工程师", "entry": "全部页面", "operations": ["按清单走查"], "dataScope": "—"},
        ],
        "glossary": [
            {"term": "轻提示 toast", "definition": "非阻断式反馈，2 秒自动消失，用于成功/轻量失败", "aliases": ["消息提示"], "forbidden": ["弹窗"]},
            {"term": "确认弹窗", "definition": "阻断式，必须显式确认/取消，用于不可逆操作", "aliases": ["Modal", "对话框"], "forbidden": ["toast"]},
            {"term": "空态", "definition": "列表无数据时的占位视图，必须含原因说明与下一步操作", "aliases": ["Empty"], "forbidden": ["空白页"]},
        ],
        "nfr": [
            {"category": "一致性", "metric": "提示形式覆盖", "target": "不可逆操作 100% 使用确认弹窗；成功反馈 100% 使用 toast", "measure": "逐页走查清单"},
            {"category": "可访问性", "metric": "键盘可达", "target": "弹窗可用 Esc 关闭、Tab 焦点不逃逸", "measure": "键盘走查"},
        ],
        "invariants": ["同一操作不得同时出现 toast 与 Modal 两种反馈"],
        "deps": [{"name": "前端 UI 组件库", "type": "内部", "assumption": "Toast/Modal/Empty 组件统一封装", "fallback": "各页面自实现，需补规范"}],
        "fixture": "任意列表页与表单页可访问",
        "data_assert": "无数据写入（纯界面约束）",
        "neg_cases": [
            {"scenario": "删除操作无二次确认", "feedback": "走查不通过，记为缺陷", "rollback": "—", "retryable": "—"},
            {"scenario": "空列表显示空白页", "feedback": "走查不通过，要求补空态", "rollback": "—", "retryable": "—"},
        ],
    },
}

DEFAULT_SPEC: dict = {
    "problem": "该需求由代码逆向还原得到，业务痛点未在源码中显式表达，需产品确认。",
    "value": "按需求描述实现对应能力，具体度量指标待产品补充。",
    "consequence": "缺失该能力会导致对应业务链路中断。",
    "out_of_scope": ["待产品确认"],
    "roles": [{"role": "系统用户", "entry": "—", "operations": ["待确认"], "dataScope": "待确认"}],
    "glossary": [],
    "nfr": [
        {"category": "性能", "metric": "接口 P95", "target": "≤ 500ms", "measure": "分接口 k6 p95"},
        {"category": "安全", "metric": "鉴权", "target": "受保护接口未携带有效令牌返回 401", "measure": "无 token 调用"},
    ],
    "invariants": [],
    "deps": [{"name": "PostgreSQL 16", "type": "存储", "assumption": "相关表可读写", "fallback": "接口返回 500 并记录 ERROR"}],
    "fixture": "相关前置数据已构造（详见数据字典）",
    "data_assert": "相关表按接口契约写入预期字段",
    "neg_cases": [
        {"scenario": "未携带令牌", "feedback": "HTTP 401，code=40103", "rollback": "无", "retryable": "登录后重试"},
        {"scenario": "必填参数缺失", "feedback": "HTTP 400，code=40000", "rollback": "不写库", "retryable": "补齐参数"},
    ],
}


def spec_for(domain: str) -> dict:
    return DOMAIN_SPEC.get(domain, DEFAULT_SPEC)
