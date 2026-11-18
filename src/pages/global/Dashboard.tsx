import { useNavigate } from "react-router-dom";
import { dashboardApi } from "@/api";
import type { DashboardData } from "@/api/types";
import { useAsync } from "@/hooks/useAsync";
import { useApp } from "@/store/app";
import { Bars, Btn, Card, Icon, Select, Skeleton, Stat, Tag } from "@/components/ui";

const STAT_META = [
  { icon: "folder" as const, hint: "当前可访问的项目" },
  { icon: "sparkles" as const, hint: "较上周 +18%" },
  { icon: "check" as const, hint: "近 7 天执行结果" },
  { icon: "database" as const, hint: "较上月 -24%" },
];

export function Dashboard() {
  const { data, loading, error, reload } = useAsync<DashboardData | null>(() => dashboardApi.get(), [], null);
  const navigate = useNavigate();
  const { projectId } = useApp();

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-44 w-full rounded-2xl" />
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-32 rounded-card" />)}</div>
        <div className="grid gap-4 xl:grid-cols-3"><Skeleton className="h-72 rounded-card xl:col-span-2" /><Skeleton className="h-72 rounded-card" /></div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <Card>
        <div className="flex min-h-60 flex-col items-center justify-center gap-3 text-center">
          <div className="grid h-11 w-11 place-items-center rounded-full bg-rose-50 text-rose-600"><Icon name="activity" size={20} /></div>
          <div className="text-[14px] font-medium text-ink-800">工作台加载失败</div>
          <div className="max-w-md text-[12px] leading-5 text-ink-500">{error ?? "请检查网络或后端服务后重试。"}</div>
          <Btn size="sm" onClick={reload}>重新加载</Btn>
        </div>
      </Card>
    );
  }

  const totalTokens = data.tokenTrend.reduce((sum, value) => sum + value, 0);

  return (
    <div className="space-y-4">
      <section className="relative overflow-hidden rounded-2xl bg-ink-950 p-6 text-white shadow-card">
        <div className="app-grid-bg pointer-events-none absolute inset-0 opacity-25" />
        <div className="pointer-events-none absolute -right-16 -top-24 h-64 w-64 rounded-full bg-brand-500/25 blur-3xl" />
        <div className="relative flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[10px] font-medium text-ink-300">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              系统运行正常
              <span className="text-ink-500">·</span>
              <span>2 个任务进行中</span>
            </div>
            <h2 className="mt-4 text-[26px] font-semibold tracking-[-0.03em]">早上好，张伟</h2>
            <p className="mt-2 max-w-xl text-[13px] leading-6 text-ink-300">
              你有 <span className="font-medium text-white">5 项待办</span>、<span className="font-medium text-white">2 个生成任务</span>正在运行。建议先处理支付中台的接口回归失败。
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Btn onClick={() => navigate(`/project/${projectId}/requirements`)}>+ 新建需求</Btn>
            <Btn v="secondary" onClick={() => navigate(`/project/${projectId}/testcases/generate`)}>+ 新建生成任务</Btn>
            <Btn className="border-white/10 bg-white/5 text-ink-200 hover:bg-white/10 hover:text-white" onClick={() => navigate(`/project/${projectId}/ai/workflow`)}>+ 新建工作流</Btn>
          </div>
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {data.stats.map((stat, index) => (
          <Stat key={stat.label} label={stat.label} value={stat.value} delta={stat.delta} up={stat.up} hint={STAT_META[index]?.hint} icon={<Icon name={STAT_META[index]?.icon ?? "activity"} size={16} />} />
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card
          title="Token 与算力消耗趋势"
          className="xl:col-span-2"
          extra={<Select opts={["近 7 天", "近 30 天"]} />}
        >
          <div className="mb-2 flex items-end justify-between gap-4">
            <div>
              <div className="text-[11px] text-ink-500">本周累计</div>
              <div className="mt-1 flex items-baseline gap-2">
                <span className="tabular-nums text-[24px] font-semibold tracking-[-0.03em] text-ink-900">{totalTokens.toFixed(1)}M</span>
                <span className="rounded-md bg-emerald-50 px-1.5 py-0.5 text-[11px] font-medium text-emerald-700">↓ 24%</span>
              </div>
            </div>
            <div className="flex items-center gap-4 text-[11px] text-ink-500">
              <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-brand-500" />Token</span>
              <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-ink-200" />基线</span>
            </div>
          </div>
          <Bars data={data.tokenTrend} labels={["一", "二", "三", "四", "五", "六", "日"]} />
        </Card>

        <Card title="告警提示" extra={<span className="text-[11px] text-ink-500">{data.alerts.length} 条</span>}>
          <div className="space-y-1">
            {data.alerts.map((alert) => (
              <div key={alert.text} className="flex items-start gap-2.5 rounded-lg px-2 py-3 transition-colors hover:bg-ink-50">
                <Tag t={alert.level} />
                <div className="min-w-0 flex-1 text-[12px] leading-5 text-ink-700">{alert.text}</div>
                <Icon name="chevron-right" size={14} className="mt-0.5 shrink-0 text-ink-300" />
              </div>
            ))}
            {data.alerts.length === 0 && <div className="py-10 text-center text-[12px] text-ink-500">暂无告警</div>}
          </div>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card title="我的项目" extra={<button onClick={() => navigate("/project/" + projectId + "/overview")} className="text-[11px] font-medium text-brand-600 hover:text-brand-700">进入项目</button>}>
          <div className="space-y-1">
            {data.projects.map((project) => (
              <button key={project.id} onClick={() => navigate(`/project/${project.id}/overview`)} className="group flex w-full items-center gap-3 rounded-lg px-2 py-2.5 text-left transition-colors hover:bg-ink-50">
                <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-50 text-[11px] font-semibold text-brand-600">{project.name.slice(0, 1)}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[12px] font-medium text-ink-800">{project.name}</span>
                  <span className="mt-0.5 block text-[11px] text-ink-500">{project.caseCount} 条用例</span>
                </span>
                <Icon name="chevron-right" size={14} className="text-ink-300 transition-transform group-hover:translate-x-0.5 group-hover:text-brand-500" />
              </button>
            ))}
          </div>
        </Card>

        <Card title="待办任务" extra={<span className="text-[11px] text-ink-500">{data.todos.length} 项</span>}>
          <div className="space-y-1">
            {data.todos.map((todo) => (
              <label key={todo} className="flex cursor-pointer items-start gap-2.5 rounded-lg px-2 py-2.5 text-[12px] leading-5 text-ink-700 hover:bg-ink-50">
                <input type="checkbox" className="mt-1 h-3.5 w-3.5 rounded border-ink-300 accent-brand-500" />
                <span>{todo}</span>
              </label>
            ))}
            {data.todos.length === 0 && <div className="py-10 text-center text-[12px] text-ink-500">今天没有待办</div>}
          </div>
        </Card>

        <Card title="近期动态">
          <div className="space-y-3">
            {data.activities.map((activity, index) => (
              <div key={`${activity.user}-${activity.action}`} className="flex items-start gap-2.5">
                <span className={`mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full text-[10px] font-semibold ${index % 2 === 0 ? "bg-brand-50 text-brand-600" : "bg-emerald-50 text-emerald-700"}`}>{activity.user.slice(0, 1)}</span>
                <div className="min-w-0 flex-1">
                  <div className="text-[12px] leading-5 text-ink-700"><span className="font-medium text-ink-900">{activity.user}</span> {activity.action}</div>
                  <div className="mt-0.5 text-[11px] text-ink-500">{activity.time}</div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
