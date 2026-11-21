from __future__ import annotations

import base64
import io
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
SCREENS = ROOT / "design" / "baseline" / "screens"
OUT = ROOT / "design" / "baseline"

GROUPS = {
    "auth": "认证",
    "global": "全局层",
    "core": "项目层 · 核心流程",
    "automation": "项目层 · 自动化",
    "ai": "项目层 · AI 与知识",
    "admin": "管理员层",
}

PAGES = [
    ("01-login.png", "auth", "登录", "/login", "邀请制登录入口，邮箱 + 密码", "default", "需补拍错误提示、禁用态"),
    ("02-dashboard.png", "global", "工作台", "/dashboard", "全局指标、待办、告警、近期动态", "default", "图表区为当前实现状态"),
    ("03-project-overview.png", "core", "项目概览", "/project/:pid/overview", "项目健康度、用例与执行统计", "default", ""),
    ("04-requirements-list.png", "core", "需求列表", "/project/:pid/requirements", "按业务模块分组的需求树、筛选、上传", "default", "当前项目数据 77 条"),
    ("05-requirement-detail.png", "core", "需求详情", "/project/:pid/requirements/:rid", "需求信息 + AI 设计生成/原型/接口", "default", "右侧工作区为空态"),
    ("06-testcases-list.png", "core", "用例列表", "/project/:pid/testcases", "测试用例表格、导入导出", "default", ""),
    ("07-testcases-generate.png", "core", "AI 生成用例", "/project/:pid/testcases/generate", "配置生成输入、生成结果", "default", ""),
    ("08-testcases-review.png", "core", "用例评审", "/project/:pid/testcases/review", "可编辑评审、通过保存", "default", ""),
    ("09-api-manage.png", "automation", "接口管理", "/project/:pid/api", "接口目录 + 接口表格", "empty", "当前为空状态，需要补拍有数据状态"),
    ("10-api-debug.png", "automation", "调试面板", "/project/:pid/api/debug", "请求编辑、响应与断言", "default", ""),
    ("11-api-suites.png", "automation", "套件与定时任务", "/project/:pid/api/suites", "套件、定时计划与执行", "default", ""),
    ("12-api-reports.png", "automation", "执行报告", "/project/:pid/api/reports", "报告列表与结果", "default", ""),
    ("13-webui-elements.png", "automation", "元素库", "/project/:pid/webui", "WebUI 元素与定位器", "default", ""),
    ("14-webui-scripts.png", "automation", "用例脚本", "/project/:pid/webui/scripts", "脚本列表与编辑器入口", "default", ""),
    ("15-webui-recorder.png", "automation", "录制回放", "/project/:pid/webui/recorder", "录制器与步骤回放", "default", ""),
    ("16-webui-runs.png", "automation", "执行记录", "/project/:pid/webui/runs", "WebUI 运行记录", "default", ""),
    ("17-app-devices.png", "automation", "设备管理", "/project/:pid/app", "App 设备与状态", "default", ""),
    ("18-app-flow.png", "automation", "UI Flow 编排", "/project/:pid/app/flow", "节点画布与配置", "default", "画布空态"),
    ("19-app-runs.png", "automation", "执行记录", "/project/:pid/app/runs", "App 运行记录", "default", ""),
    ("20-ai-chat.png", "ai", "对话助手", "/project/:pid/ai/chat", "知识库问答、引用与工具调用", "default", "已有会话数据"),
    ("21-ai-workflow.png", "ai", "工作流编排器", "/project/:pid/ai/workflow", "节点库、画布、节点配置", "default", ""),
    ("22-knowledge-list.png", "ai", "知识库列表", "/project/:pid/knowledge", "知识库与文档数量", "default", ""),
    ("23-knowledge-documents.png", "ai", "文档管理", "/project/:pid/knowledge/documents", "文档上传、解析、切片", "default", ""),
    ("24-knowledge-recall.png", "ai", "召回测试", "/project/:pid/knowledge/recall", "检索查询与召回结果", "default", ""),
    ("25-knowledge-learning.png", "ai", "学习中心", "/project/:pid/knowledge/learning", "课程内容与学习进度", "default", ""),
    ("26-task-list.png", "ai", "任务列表", "/project/:pid/tasks", "后台任务、进度与重试", "default", ""),
    ("27-agent-eval.png", "ai", "Agent 评测", "/project/:pid/tasks/agent-eval", "评测集与结果", "default", ""),
    ("28-version-compare.png", "ai", "版本对比", "/project/:pid/tasks/compare", "版本差异与变更", "default", ""),
    ("29-skills-list.png", "global", "技能市场", "/skills/list", "技能列表、导入、编辑", "default", ""),
    ("30-mcp-servers.png", "global", "MCP 服务", "/mcp", "MCP 服务登记、连接测试、工具列表", "default", ""),
    ("31-team-members.png", "global", "团队成员", "/team/members", "成员列表、邀请、角色", "default", ""),
    ("32-team-roles.png", "global", "角色权限", "/team/roles", "角色权限矩阵", "default", ""),
    ("33-team-assignments.png", "global", "项目分配", "/team/assignments", "成员与项目关系", "default", ""),
    ("34-profile-info.png", "global", "个人信息", "/profile/info", "个人资料与偏好", "default", ""),
    ("35-profile-security.png", "global", "安全设置", "/profile/security", "密码、会话与安全", "default", ""),
    ("36-profile-assets.png", "global", "我的资产", "/profile/assets", "产物与资产", "default", ""),
    ("37-profile-keys.png", "global", "API Key", "/profile/keys", "个人密钥管理", "default", ""),
    ("38-admin-providers.png", "admin", "模型供应商", "/admin/models/providers", "模型供应商与密钥", "default", ""),
    ("39-admin-routing.png", "admin", "模型路由规则", "/admin/models/routing", "模型路由与规则", "default", ""),
    ("40-admin-connection-test.png", "admin", "连接测试", "/admin/models/test", "模型连通性测试", "default", ""),
    ("41-admin-users.png", "admin", "用户管理", "/admin/system/users", "平台用户与角色", "default", ""),
    ("42-admin-health.png", "admin", "环境检测", "/admin/system/health", "服务与依赖健康", "default", ""),
    ("43-admin-notifications.png", "admin", "通知配置", "/admin/system/notifications", "通知渠道与规则", "default", ""),
    ("44-admin-audit.png", "admin", "审计日志", "/admin/audit/logs", "操作审计与筛选", "default", ""),
]

META = {
    "project": "AI 测试开发平台",
    "createdAt": "2026-11-16",
    "gitCommit": "83aa7b9",
    "viewport": {"width": 1440, "height": 900},
    "baseUrl": "http://127.0.0.1:8443",
    "state": "当前实现，未做视觉美化",
}


def build_manifest():
    screens = []
    for idx, (file, group, title, route, purpose, state, notes) in enumerate(PAGES, 1):
        screens.append({
            "id": f"S{idx:02d}",
            "file": f"screens/{file}",
            "group": GROUPS[group],
            "title": title,
            "route": route,
            "purpose": purpose,
            "state": state,
            "notes": notes,
        })
    data = {**META, "screens": screens}
    (OUT / "manifest.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def build_inventory(data):
    lines = ["# 页面基线清单", "", f"- 生成日期：{data['createdAt']}", f"- 代码版本：`{data['gitCommit']}`", f"- 视口：{data['viewport']['width']}×{data['viewport']['height']}", f"- 截图目录：`design/baseline/screens/`", "", "> 当前截图记录的是“实现现状”，不是目标设计。优化稿请放在 Figma，并以 approved 帧为准。", ""]
    current = None
    for s in data["screens"]:
        if s["group"] != current:
            if current is not None:
                lines.append("")
            current = s["group"]
            lines += [f"## {current}", "", "| ID | 页面 | 路由 | 截图 | 说明 |", "|---|---|---|---|---|"]
        lines.append(f"| {s['id']} | {s['title']} | `{s['route']}` | `{s['file']}` | {s['purpose']}{('；' + s['notes']) if s['notes'] else ''} |")
    lines += ["", "## 待补拍状态", "", "- 登录错误提示 / 禁用态", "- 需求上传弹窗、拆分草案弹窗", "- 用例评审保存成功 / 失败", "- 接口管理的“有数据”状态", "- 各类空状态、加载骨架、权限不足、网络错误", "- 1024px 与 390px 响应式基线", ""]
    (ROOT / "design" / "page-inventory.md").write_text("\n".join(lines), encoding="utf-8")


def font(size: int, bold: bool = False):
    candidate = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
    return ImageFont.truetype(candidate, size)


def build_contact_sheet(data):
    cols = 5
    thumb_w, thumb_h = 400, 250
    gap_x, gap_y = 28, 38
    margin = 80
    section_h = 66
    header_h = 150
    width = margin * 2 + cols * thumb_w + (cols - 1) * gap_x
    # compute height by group rows
    groups = []
    for key, label in GROUPS.items():
        items = [s for s in data["screens"] if s["group"] == label]
        if items:
            groups.append((label, items))
    rows = sum((len(items) + cols - 1) // cols for _, items in groups)
    height = header_h + rows * (thumb_h + gap_y) + len(groups) * section_h + margin

    img = Image.new("RGB", (width, height), "#F8FAFC")
    d = ImageDraw.Draw(img)
    d.text((margin, 50), "AI 测试开发平台 — Baseline Snapshot", font=font(36, True), fill="#0F172A")
    d.text((margin, 100), f"{data['createdAt']} · {data['viewport']['width']}×{data['viewport']['height']} · {len(data['screens'])} screens · commit {data['gitCommit']}", font=font(18), fill="#64748B")

    y = header_h
    for label, items in groups:
        d.rectangle([margin, y, width - margin, y + 38], fill="#0F172A")
        d.text((margin + 18, y + 9), f"{label}  /  {len(items)} screens", font=font(18, True), fill="#FFFFFF")
        y += section_h
        for i, s in enumerate(items):
            col = i % cols
            row = i // cols
            x = margin + col * (thumb_w + gap_x)
            yy = y + row * (thumb_h + gap_y)
            d.rounded_rectangle([x - 1, yy - 1, x + thumb_w + 1, yy + thumb_h + 1], radius=10, outline="#CBD5E1", fill="#FFFFFF")
            thumb = Image.open(SCREENS / Path(s["file"]).name).convert("RGB")
            thumb.thumbnail((thumb_w - 8, thumb_h - 8))
            img.paste(thumb, (x + (thumb_w - thumb.width) // 2, yy + 4))
            d.text((x, yy + thumb_h + 10), f"{s['id']}  {s['title']}", font=font(16, True), fill="#0F172A")
            d.text((x, yy + thumb_h + 31), s["route"][:52], font=font(12), fill="#64748B")
        y += ((len(items) + cols - 1) // cols) * (thumb_h + gap_y)

    img.save(OUT / "contact-sheet.png", optimize=True)

    # SVG board (thumbnails as embedded JPEG)
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           f'<rect width="{width}" height="{height}" fill="#F8FAFC"/>',
           f'<text x="{margin}" y="66" font-family="Inter, PingFang SC, sans-serif" font-size="36" font-weight="700" fill="#0F172A">AI 测试开发平台 — Baseline Snapshot</text>',
           f'<text x="{margin}" y="106" font-family="Inter, PingFang SC, sans-serif" font-size="18" fill="#64748B">{data["createdAt"]} · {data["viewport"]["width"]}×{data["viewport"]["height"]} · {len(data["screens"])} screens</text>']
    y = header_h
    for label, items in groups:
        svg.append(f'<rect x="{margin}" y="{y}" width="{width - margin*2}" height="38" rx="6" fill="#0F172A"/>')
        svg.append(f'<text x="{margin+18}" y="{y+26}" font-family="Inter, PingFang SC, sans-serif" font-size="18" font-weight="700" fill="#FFFFFF">{label} / {len(items)} screens</text>')
        y += section_h
        for i, s in enumerate(items):
            col = i % cols
            row = i // cols
            x = margin + col * (thumb_w + gap_x)
            yy = y + row * (thumb_h + gap_y)
            thumb = Image.open(SCREENS / Path(s["file"]).name).convert("RGB")
            thumb.thumbnail((thumb_w - 8, thumb_h - 8))
            buf = io.BytesIO()
            thumb.save(buf, format="JPEG", quality=82, optimize=True)
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            svg.append(f'<rect x="{x-1}" y="{yy-1}" width="{thumb_w+2}" height="{thumb_h+2}" rx="10" fill="#FFFFFF" stroke="#CBD5E1"/>')
            svg.append(f'<image x="{x+4}" y="{yy+4}" width="{thumb.width}" height="{thumb.height}" href="data:image/jpeg;base64,{b64}"/>')
            svg.append(f'<text x="{x}" y="{yy+thumb_h+26}" font-family="Inter, PingFang SC, sans-serif" font-size="16" font-weight="700" fill="#0F172A">{s["id"]}  {s["title"]}</text>')
            svg.append(f'<text x="{x}" y="{yy+thumb_h+47}" font-family="Inter, PingFang SC, sans-serif" font-size="12" fill="#64748B">{s["route"][:52]}</text>')
        y += ((len(items) + cols - 1) // cols) * (thumb_h + gap_y)
    svg.append("</svg>")
    (OUT / "contact-sheet.svg").write_text("\n".join(svg), encoding="utf-8")


if __name__ == "__main__":
    data = build_manifest()
    build_inventory(data)
    build_contact_sheet(data)
    print("manifest screens:", len(data["screens"]))
