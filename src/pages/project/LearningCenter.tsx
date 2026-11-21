import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import courseRaw from "@/content/llm-wiki-course.json";
import { useApp } from "@/store/app";
import { Btn, Card, Input, Progress, Stat, Tag } from "@/components/ui";
import { cx } from "@/lib/cx";

type Lesson = {
  id: string;
  kind: "lesson" | "note";
  chapter: string;
  title: string;
  summary: string;
  duration: number;
  level: string;
  path: string;
  html: string;
  plain: string;
};

type CourseData = {
  generatedAt: string;
  source: string;
  totalMinutes: number;
  lessons: Lesson[];
};

const COURSE = courseRaw as CourseData;
const LESSONS = COURSE.lessons.filter((item) => item.kind === "lesson");
const NOTES = COURSE.lessons.filter((item) => item.kind === "note");

type Filter = "all" | "lesson" | "note";

function readProgress(key: string): Set<string> {
  try {
    const raw = localStorage.getItem(key);
    return new Set<string>(raw ? (JSON.parse(raw) as string[]) : []);
  } catch {
    return new Set<string>();
  }
}

function chapterOrder(items: Lesson[]): string[] {
  return [...new Set(items.map((item) => item.chapter))];
}

export function LearningCenter() {
  const { pid } = useParams<{ pid: string }>();
  const { toast } = useApp();
  const progressKey = `ast.llm-wiki.progress:${pid ?? "default"}`;
  const [completed, setCompleted] = useState<Set<string>>(() => readProgress(progressKey));
  const [selectedId, setSelectedId] = useState<string>(() => LESSONS[0]?.id ?? "");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const articleRef = useRef<HTMLElement>(null);

  useEffect(() => {
    setCompleted(readProgress(progressKey));
  }, [progressKey]);

  const visible = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    return COURSE.lessons.filter((item) => {
      if (filter !== "all" && item.kind !== filter) return false;
      if (!keyword) return true;
      return `${item.title} ${item.summary} ${item.chapter} ${item.plain}`.toLowerCase().includes(keyword);
    });
  }, [filter, query]);

  useEffect(() => {
    if (visible.length > 0 && !visible.some((item) => item.id === selectedId)) {
      setSelectedId(visible[0].id);
    }
  }, [visible, selectedId]);

  const selected = COURSE.lessons.find((item) => item.id === selectedId) ?? visible[0] ?? COURSE.lessons[0];
  const selectedIndex = selected ? COURSE.lessons.findIndex((item) => item.id === selected.id) : -1;
  const prev = selectedIndex > 0 ? COURSE.lessons[selectedIndex - 1] : null;
  const next = selectedIndex >= 0 && selectedIndex < COURSE.lessons.length - 1 ? COURSE.lessons[selectedIndex + 1] : null;
  const donePercent = COURSE.lessons.length ? Math.round((completed.size / COURSE.lessons.length) * 100) : 0;

  const select = (id: string) => {
    setSelectedId(id);
    window.setTimeout(() => articleRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
  };

  const toggleDone = (id: string) => {
    const nextSet = new Set(completed);
    if (nextSet.has(id)) nextSet.delete(id);
    else nextSet.add(id);
    setCompleted(nextSet);
    try {
      localStorage.setItem(progressKey, JSON.stringify([...nextSet]));
    } catch {
      /* localStorage 不可用时仅保留内存状态 */
    }
    toast(nextSet.has(id) ? "已标记完成" : "已取消完成");
  };

  const groups = chapterOrder(visible);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-4 gap-4">
        <Stat label="课程" value={LESSONS.length} />
        <Stat label="学习笔记" value={NOTES.length} />
        <Stat label="总时长" value={`${COURSE.totalMinutes} 分钟`} />
        <Stat label="我的进度" value={`${donePercent}%`} />
      </div>

      <div className="grid grid-cols-[260px_minmax(0,1fr)_240px] gap-4 items-start">
        <Card className="sticky top-4">
          <div className="space-y-3">
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索课程 / 知识点"
              className="w-full"
            />
            <div className="flex gap-1">
              {([
                ["all", `全部 ${COURSE.lessons.length}`],
                ["lesson", `课程 ${LESSONS.length}`],
                ["note", `笔记 ${NOTES.length}`],
              ] as Array<[Filter, string]>).map(([value, label]) => (
                <button
                  key={value}
                  onClick={() => setFilter(value)}
                  className={cx(
                    "flex-1 h-7 rounded text-[11px] border",
                    filter === value
                      ? "border-brand-500 bg-brand-50 text-brand-700"
                      : "border-line text-ink-600 hover:border-brand-300",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="max-h-[calc(100vh-330px)] overflow-y-auto pr-1 space-y-3">
              {groups.length === 0 && <div className="text-xs text-ink-500 py-8 text-center">没有匹配的课程</div>}
              {groups.map((chapter) => (
                <div key={chapter}>
                  <div className="text-[11px] uppercase tracking-wide text-ink-500 mb-1">{chapter}</div>
                  <div className="space-y-0.5">
                    {visible
                      .filter((item) => item.chapter === chapter)
                      .map((item) => (
                        <button
                          key={item.id}
                          onClick={() => select(item.id)}
                          className={cx(
                            "w-full text-left px-2 py-1.5 rounded text-xs flex items-start gap-2",
                            selected?.id === item.id
                              ? "bg-brand-50 text-brand-700"
                              : "text-ink-600 hover:bg-ink-50",
                          )}
                        >
                          <span
                            className={cx(
                              "mt-0.5 w-3.5 h-3.5 rounded-full border grid place-items-center shrink-0 text-[8px]",
                              completed.has(item.id)
                                ? "bg-emerald-500 border-emerald-500 text-white"
                                : "border-ink-300",
                            )}
                          >
                            {completed.has(item.id) ? "✓" : ""}
                          </span>
                          <span className="min-w-0">
                            <span className="block leading-4">{item.title}</span>
                            <span className="block text-[10px] text-ink-400 mt-0.5">
                              {item.id} · {item.duration}m
                            </span>
                          </span>
                        </button>
                      ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </Card>

        <article ref={articleRef} className="bg-white rounded-lg border border-line shadow-sm min-h-[600px]">
          {selected ? (
            <>
              <header className="px-6 py-4 border-b border-ink-100">
                <div className="flex items-center gap-2 text-[11px] text-ink-500">
                  <Tag t={selected.kind === "lesson" ? "课程" : "笔记"} c={selected.kind === "lesson" ? "blue" : "amber"} />
                  <span>{selected.chapter}</span>
                  <span>·</span>
                  <span>{selected.duration} 分钟</span>
                  <span>·</span>
                  <span>{selected.level}</span>
                  <div className="flex-1" />
                  <span className="font-mono">{selected.id}</span>
                </div>
                <h2 className="text-lg font-semibold text-ink-900 mt-2">{selected.title}</h2>
                <p className="text-xs text-ink-500 mt-1">{selected.summary}</p>
              </header>

              <div className="px-6 py-5">
                <div className="course-content" dangerouslySetInnerHTML={{ __html: selected.html }} />
              </div>

              <footer className="px-6 py-4 border-t border-ink-100 flex items-center gap-2">
                <Btn v="ghost" disabled={!prev} onClick={() => prev && select(prev.id)}>
                  ← 上一课
                </Btn>
                <Btn
                  v={completed.has(selected.id) ? "ghost" : "primary"}
                  onClick={() => toggleDone(selected.id)}
                >
                  {completed.has(selected.id) ? "取消完成" : "标记完成"}
                </Btn>
                <div className="flex-1" />
                <Btn v="ghost" disabled={!next} onClick={() => next && select(next.id)}>
                  下一课 →
                </Btn>
              </footer>
            </>
          ) : (
            <div className="h-60 grid place-items-center text-xs text-ink-500">选择左侧课程开始学习</div>
          )}
        </article>

        <div className="space-y-4 sticky top-4">
          <Card title="学习进度">
            <div className="space-y-2">
              <div className="flex items-end justify-between">
                <span className="text-2xl font-semibold text-ink-900">{donePercent}%</span>
                <span className="text-[11px] text-ink-500">{completed.size}/{COURSE.lessons.length} 完成</span>
              </div>
              <Progress value={donePercent} />
              <div className="text-[11px] text-ink-500 leading-5 pt-1">
                进度保存在当前浏览器；换项目空间会单独统计。
              </div>
            </div>
          </Card>

          <Card title="配套资产">
            <div className="space-y-1 text-xs">
              <a className="block py-1 text-brand-600 hover:underline" href="http://127.0.0.1:9092/graph.html" target="_blank" rel="noreferrer">
                知识图谱 graph.html ↗
              </a>
              <Link className="block py-1 text-brand-600 hover:underline" to={`/project/${pid}/knowledge/documents?kb=${encodeURIComponent("LLM-wiki 学习中心")}`}>
                课件知识库文档
              </Link>
              <Link className="block py-1 text-brand-600 hover:underline" to={`/project/${pid}/knowledge/recall?kb=${encodeURIComponent("LLM-wiki 学习中心")}`}>
                召回测试
              </Link>
              <Link className="block py-1 text-brand-600 hover:underline" to={`/project/${pid}/requirements`}>
                需求列表
              </Link>
              <Link className="block py-1 text-brand-600 hover:underline" to={`/project/${pid}/api`}>
                接口管理
              </Link>
              <Link className="block py-1 text-brand-600 hover:underline" to={`/project/${pid}/ai/chat`}>
                问 AI 助手
              </Link>
            </div>
          </Card>

          <Card title="学习建议">
            <ol className="text-[11px] text-ink-600 leading-5 list-decimal pl-4 space-y-1">
              <li>先读 L00-L02，建立系统地图。</li>
              <li>用 L03-L06 做一次需求追溯。</li>
              <li>在 L07-L08 跑图谱和召回。</li>
              <li>用 L09-L10 写影响分析和复盘。</li>
              <li>L11-L12 补自动化与面试表达。</li>
            </ol>
          </Card>
        </div>
      </div>
    </div>
  );
}
