import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { notifications } from "@/config/notifications";
import { useApp } from "@/store/app";
import { Icon, Tag } from "@/components/ui";

export function NotificationCenter() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const { projectId } = useApp();

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="relative grid h-8 w-8 place-items-center rounded-lg text-ink-300 transition-colors hover:bg-white/5 hover:text-white"
        aria-label={`通知，${notifications.length} 条未读`}
      >
        <Icon name="bell" size={17} />
        {notifications.length > 0 && (
          <span className="absolute right-1 top-1 grid h-4 min-w-4 place-items-center rounded-full bg-rose-500 px-1 text-[9px] font-semibold text-white ring-2 ring-ink-950">
            {notifications.length}
          </span>
        )}
      </button>
      {open && (
        <>
          <button className="fixed inset-0 z-40 cursor-default" aria-label="关闭通知" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-10 z-50 w-80 overflow-hidden rounded-xl border border-line bg-white text-ink-700 shadow-pop">
            <div className="flex items-center justify-between border-b border-ink-100 px-4 py-3">
              <div className="text-[13px] font-semibold text-ink-900">通知</div>
              <span className="text-[11px] text-ink-500">{notifications.length} 条未读</span>
            </div>
            <div className="max-h-80 overflow-y-auto">
              {notifications.length === 0 && <div className="px-4 py-8 text-center text-xs text-ink-500">暂无通知</div>}
              {notifications.map((n) => (
                <button
                  key={n.id}
                  onClick={() => { setOpen(false); navigate(`/project/${projectId}${n.to}`); }}
                  className="w-full border-b border-ink-100 px-4 py-3 text-left text-xs last:border-0 hover:bg-ink-50"
                >
                  <Tag t={n.title} c={n.tone} />
                  <div className="mt-1.5 leading-5 text-ink-600">{n.detail}</div>
                </button>
              ))}
            </div>
            <button
              onClick={() => { setOpen(false); navigate(`/project/${projectId}/tasks`); }}
              className="w-full border-t border-ink-100 py-2.5 text-center text-[12px] font-medium text-brand-600 hover:bg-brand-50"
            >
              查看全部任务
            </button>
          </div>
        </>
      )}
    </div>
  );
}
