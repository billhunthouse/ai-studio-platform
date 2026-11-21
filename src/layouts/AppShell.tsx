import { Suspense, useEffect } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import type { Layer } from "@/api/types";
import { MENUS, resolveNav, tabHref, type MenuItem } from "@/config/menu";
import { useApp } from "@/store/app";
import { useAuth } from "@/store/auth";
import { cx } from "@/lib/cx";
import { NotificationCenter, ProjectSwitcher, TaskDock } from "@/components/business";
import { Icon, ToastStack, type IconName } from "@/components/ui";

const MENU_ICONS: Record<string, IconName> = {
  dashboard: "dashboard",
  skills: "sparkles",
  mcp: "server",
  team: "users",
  profile: "settings",
  overview: "dashboard",
  requirements: "folder",
  testcases: "check",
  api: "api",
  webui: "monitor",
  app: "phone",
  ai: "sparkles",
  knowledge: "book",
  tasks: "clipboard",
  models: "database",
  system: "activity",
  audit: "shield",
};

const PAGE_HINTS: Record<string, string> = {
  dashboard: "统一查看项目健康度、待办与 AI 生成任务",
  skills: "管理可复用的技能与 MCP 工具",
  mcp: "登记并测试外部 MCP 服务",
  team: "管理成员、角色与项目分配",
  profile: "管理个人资料、安全与访问密钥",
  overview: "项目健康度、用例与执行趋势",
  requirements: "按业务模块组织需求，支持上传、拆分与生成用例",
  testcases: "编写、评审与导入导出测试用例",
  api: "管理接口定义、调试与执行报告",
  webui: "维护元素库、脚本、录制与执行记录",
  app: "管理设备、UI Flow 与 App 执行记录",
  ai: "用知识库上下文驱动对话与工作流",
  knowledge: "管理知识库文档、切片与召回测试",
  tasks: "查看后台任务、Agent 评测与版本对比",
  models: "配置模型供应商、路由与连通性",
  system: "管理平台用户、环境与通知",
  audit: "查看平台操作审计与变更记录",
};

const SIDEBAR_GROUPS: Record<Layer, { label: string; keys: string[] }[]> = {
  global: [
    { label: "概览", keys: ["dashboard"] },
    { label: "能力", keys: ["skills", "mcp"] },
    { label: "组织", keys: ["team"] },
    { label: "账户", keys: ["profile"] },
  ],
  project: [
    { label: "核心流程", keys: ["overview", "requirements", "trace", "testcases"] },
    { label: "自动化", keys: ["api", "webui", "app"] },
    { label: "智能与知识", keys: ["ai", "knowledge"] },
    { label: "交付", keys: ["tasks"] },
  ],
  admin: [
    { label: "模型", keys: ["models"] },
    { label: "系统", keys: ["system"] },
    { label: "审计", keys: ["audit"] },
  ],
};

function groupMenus(menus: MenuItem[], layer: Layer) {
  return SIDEBAR_GROUPS[layer]
    .map((group) => ({ ...group, items: menus.filter((menu) => group.keys.includes(menu.key)) }))
    .filter((group) => group.items.length > 0);
}

export function AppShell({ layer }: { layer: Layer }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { projectId, projectName, toasts, setProjectId } = useApp();
  const { user, isAdmin, logout } = useAuth();
  const nav = resolveNav(location.pathname);
  const menu = nav.menu ?? MENUS[layer][0];
  const activeTab = nav.tab?.label ?? menu.tabs[0].label;
  // hidden 的页签只用于面包屑/高亮匹配，不渲染成可点击标签（如带参数的详情页）
  const visibleTabs = menu.tabs.filter((t) => !t.hidden);
  const globalMenus = MENUS.global.filter((m) => (m.key !== "team" && m.key !== "mcp") || isAdmin);
  const layerMenus = layer === "global" ? globalMenus : MENUS[layer];
  const groups = groupMenus(layerMenus, layer);

  useEffect(() => {
    if (layer === "project" && nav.pid && nav.pid !== projectId) setProjectId(nav.pid);
  }, [layer, nav.pid, projectId, setProjectId]);

  const goTab = (tabPath: string) => navigate(tabHref(layer, projectId, tabPath));
  const goMenu = (menuKey: string) => {
    const target = MENUS[layer].find((m) => m.key === menuKey);
    if (target) goTab(target.tabs[0].path);
  };

  const globalActive = layer === "global" ? menu.key : "";
  const breadcrumb =
    layer === "project" ? `项目空间 / ${projectName} / ${menu.label}` : layer === "admin" ? `管理后台 / ${menu.label}` : `全局 / ${menu.label}`;
  const contextLabel = layer === "global" ? "全局工作空间" : layer === "project" ? projectName : "平台管理";

  return (
    <div className="flex h-screen flex-col bg-surface text-ink-800">
      <header className="flex h-14 shrink-0 items-center border-b border-white/5 bg-ink-950 px-4 text-ink-300">
        <button onClick={() => navigate("/dashboard")} className="flex w-[216px] shrink-0 items-center gap-2.5 text-left">
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-brand-500 text-white shadow-[0_0_0_1px_rgba(255,255,255,0.12),0_4px_12px_rgba(45,91,255,0.35)]">
            <Icon name="sparkles" size={15} />
          </span>
          <span className="text-[13px] font-semibold tracking-[-0.01em] text-white">AI 测试开发平台</span>
          <span className="rounded-md border border-white/10 bg-white/5 px-1.5 py-0.5 text-[9px] font-medium tracking-wide text-ink-300">Enterprise</span>
        </button>

        <nav className="flex h-full items-stretch gap-0.5">
          {globalMenus.map((item) => (
            <button
              key={item.key}
              onClick={() => navigate(tabHref("global", projectId, item.tabs[0].path))}
              className={cx(
                "relative px-3 text-[12px] transition-colors",
                globalActive === item.key ? "text-white" : "text-ink-300 hover:text-white",
              )}
            >
              {item.label}
              {globalActive === item.key && <span className="absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-brand-400" />}
            </button>
          ))}
          <button
            onClick={() => navigate(projectId ? `/project/${projectId}/overview` : "/dashboard")}
            className={cx("relative px-3 text-[12px] transition-colors", layer === "project" ? "text-white" : "text-ink-300 hover:text-white")}
          >
            项目空间
            {layer === "project" && <span className="absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-brand-400" />}
          </button>
          {isAdmin && (
            <button
              onClick={() => navigate("/admin/models/providers")}
              className={cx("relative px-3 text-[12px] transition-colors", layer === "admin" ? "text-white" : "text-ink-300 hover:text-white")}
            >
              管理后台
              {layer === "admin" && <span className="absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-brand-400" />}
            </button>
          )}
        </nav>

        <div className="min-w-2 flex-1" />
        <div className="flex items-center gap-4">
          <ProjectSwitcher />
          <NotificationCenter />
          <div className="flex items-center gap-2.5 border-l border-white/10 pl-4">
            <div className="grid h-8 w-8 place-items-center rounded-full bg-gradient-to-br from-brand-400 to-brand-600 text-[11px] font-semibold text-white">{(user?.name ?? "?").slice(0, 1)}</div>
            <div className="hidden leading-tight xl:block">
              <div className="text-[12px] font-medium text-white">{user?.name ?? "未登录"}</div>
              <div className="text-[10px] text-ink-400">{user?.role ?? "-"}</div>
            </div>
            <button onClick={() => { void logout().then(() => navigate("/login")); }} className="text-[11px] text-ink-400 transition-colors hover:text-white">退出</button>
          </div>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <aside className="flex w-[232px] shrink-0 flex-col overflow-y-auto border-r border-line bg-white">
          <div className="px-5 pb-3 pt-5">
            <div className="text-[10px] font-medium uppercase tracking-[0.16em] text-ink-400">{layer === "project" ? "项目空间" : layer === "admin" ? "管理后台" : "工作空间"}</div>
            <div className="mt-1 flex items-center gap-2 text-[13px] font-semibold text-ink-800">
              <span className="h-1.5 w-1.5 rounded-full bg-brand-500" />
              <span className="truncate">{contextLabel}</span>
            </div>
          </div>

          <div className="flex-1 px-3 pb-4">
            {groups.map((group) => (
              <div key={group.label} className="pb-4">
                <div className="px-2 pb-1.5 text-[10px] font-medium tracking-[0.12em] text-ink-400">{group.label}</div>
                <div className="space-y-0.5">
                  {group.items.map((item) => {
                    const active = menu.key === item.key;
                    return (
                      <button
                        key={item.key}
                        onClick={() => goMenu(item.key)}
                        aria-current={active ? "page" : undefined}
                        className={cx(
                          "flex h-9 w-full items-center gap-2.5 rounded-lg border-l-2 px-2.5 text-left text-[13px] transition-colors",
                          active
                            ? "border-brand-500 bg-brand-50 font-medium text-brand-700"
                            : "border-transparent text-ink-600 hover:bg-ink-50 hover:text-ink-900",
                        )}
                      >
                        <Icon name={MENU_ICONS[item.key] ?? "folder"} size={16} className={active ? "text-brand-500" : "text-ink-400"} />
                        <span className="truncate">{item.label}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>

          <div className="border-t border-ink-100 px-5 py-4 text-[10px] leading-5 text-ink-400">
            <div className="flex items-center gap-1.5"><span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />服务正常</div>
            <div className="mt-1">AI Test Platform · v1.0</div>
          </div>
        </aside>

        <main className="min-w-0 flex-1 overflow-y-auto">
          <div className="border-b border-line bg-white px-6 pt-4 lg:px-8">
            <div className="text-[11px] text-ink-500">{breadcrumb}</div>
            <div className="mt-1 flex items-end justify-between gap-6">
              <div>
                <h1 className="text-[26px] font-semibold tracking-[-0.03em] text-ink-900">{menu.label}</h1>
                <div className="mt-1 text-[12px] text-ink-500">{PAGE_HINTS[menu.key] ?? (layer === "project" ? "当前项目的测试资产与执行情况" : layer === "admin" ? "平台级配置与治理" : "全局工作台与组织协作")}</div>
              </div>
            </div>
            {visibleTabs.length > 1 ? (
              <div className="mt-4 flex gap-6 overflow-x-auto">
                {visibleTabs.map((tab) => (
                  <button
                    key={tab.label}
                    onClick={() => goTab(tab.path)}
                    className={cx(
                      "relative whitespace-nowrap pb-3 text-[12px] transition-colors",
                      activeTab === tab.label ? "font-medium text-brand-600" : "text-ink-500 hover:text-ink-800",
                    )}
                  >
                    {tab.label}
                    {activeTab === tab.label && <span className="absolute inset-x-0 bottom-0 h-0.5 rounded-full bg-brand-500" />}
                  </button>
                ))}
              </div>
            ) : (
              <div className="h-4" />
            )}
          </div>
          <div className="mx-auto w-full max-w-[1600px] p-6 pb-16 lg:p-8">
            <Suspense fallback={<div className="grid h-40 place-items-center text-xs text-ink-500">加载中…</div>}>
              <Outlet />
            </Suspense>
          </div>
        </main>
      </div>

      <TaskDock />
      <ToastStack items={toasts} />
    </div>
  );
}
