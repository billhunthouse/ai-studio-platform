import { useNavigate } from "react-router-dom";
import { useApp, useTasks } from "@/store/app";
import { cx } from "@/lib/cx";
import { Icon } from "@/components/ui";

export function TaskDock() {
  const { dockOpen, setDockOpen, projectId } = useApp();
  const tasks = useTasks();
  const navigate = useNavigate();
  const running = tasks.filter((t) => t.status === "进行中").length;

  return (
    <div className="fixed bottom-5 right-5 z-40 w-80 overflow-hidden rounded-xl border border-line bg-white shadow-pop">
      <button onClick={() => setDockOpen(!dockOpen)} className="flex h-10 w-full items-center justify-between gap-3 px-4 text-[11px] font-medium text-ink-700">
        <span className="flex items-center gap-2">
          <Icon name="activity" size={15} className={running > 0 ? "text-brand-500" : "text-ink-400"} />
          后台任务
        </span>
        <span className="flex items-center gap-1.5 text-brand-600">
          {running} 个进行中
          <Icon name="chevron-down" size={13} className={cx("transition-transform", dockOpen && "rotate-180")} />
        </span>
      </button>
      {dockOpen && (
        <div className="max-h-64 overflow-y-auto border-t border-ink-100">
          {tasks.length === 0 && <div className="px-4 py-7 text-center text-xs text-ink-500">暂无后台任务</div>}
          {tasks.map((t) => (
            <div key={t.id} className="border-b border-ink-100 px-4 py-3 text-xs last:border-0">
              <div className="flex justify-between gap-2">
                <span className="truncate text-ink-700">{t.name}</span>
                <span className={cx("shrink-0 text-[11px]", t.status === "已完成" ? "text-emerald-600" : t.status === "失败" ? "text-rose-600" : "text-brand-600")}>
                  {t.status === "进行中" ? `${t.progress}%` : t.status}
                </span>
              </div>
              <div className="mt-2 h-1 rounded-full bg-ink-100">
                <div className={cx("h-1 rounded-full transition-all", t.status === "已完成" ? "bg-emerald-500" : t.status === "失败" ? "bg-rose-500" : "bg-brand-500")} style={{ width: `${t.progress}%` }} />
              </div>
            </div>
          ))}
          <button onClick={() => navigate(`/project/${projectId}/tasks`)} className="w-full border-t border-ink-100 py-2.5 text-center text-[11px] font-medium text-brand-600 hover:bg-brand-50">
            查看全部任务
          </button>
        </div>
      )}
    </div>
  );
}
