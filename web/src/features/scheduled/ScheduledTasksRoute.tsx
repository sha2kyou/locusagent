import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Loader2, Pencil, Trash2 } from "lucide-react";
import { Cron, type Locale as CronLocale } from "react-js-cron";
import "react-js-cron/styles.css";
import { PageContainer } from "@/components/PageContainer";
import { ReadyGate } from "@/components/ReadyGate";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/field";
import { CollapsiblePanel, CollapsibleSection, ListCard } from "@/components/ui/panel";
import { useDialogs } from "@/components/ui/dialogs";
import { useToast } from "@/components/ui/toast";
import {
  createScheduledTask,
  deleteScheduledTask,
  getTimezoneConfig,
  listScheduledTasks,
  updateScheduledTask,
} from "@/api/endpoints";
import type { ScheduledTask, ScheduleKind } from "@/api/types";
import { Empty, Loading } from "@/features/skills/SkillsRoute";
import { cn } from "@/lib/utils";

const CRON_LOCALE_ZH: CronLocale = {
  everyText: "每",
  emptyMonths: "每月",
  emptyMonthDays: "每天",
  emptyMonthDaysShort: "天",
  emptyWeekDays: "每周",
  emptyWeekDaysShort: "周",
  emptyHours: "每小时",
  emptyMinutes: "每分钟",
  emptyMinutesForHourPeriod: "分钟",
  yearOption: "年",
  monthOption: "月",
  weekOption: "周",
  dayOption: "日",
  hourOption: "小时",
  minuteOption: "分钟",
  rebootOption: "重启后",
  prefixPeriod: "周期",
  prefixMonths: "在",
  prefixMonthDays: "在",
  prefixWeekDays: "在",
  prefixWeekDaysForMonthAndYearPeriod: "在",
  prefixHours: "在",
  prefixMinutes: "在",
  prefixMinutesForHourPeriod: "在",
  suffixMinutesForHourPeriod: "分钟",
  errorInvalidCron: "Cron 表达式无效",
  clearButtonText: "清空",
  weekDays: ["周日", "周一", "周二", "周三", "周四", "周五", "周六"],
  months: ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"],
  altWeekDays: ["日", "一", "二", "三", "四", "五", "六"],
  altMonths: ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"],
};

function formatWhen(iso: string | null, tz: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  try {
    return d.toLocaleString(undefined, { timeZone: tz });
  } catch {
    return d.toLocaleString();
  }
}

function toDatetimeLocal(iso: string | null, tz: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  try {
    const fmt = new Intl.DateTimeFormat("en-CA", {
      timeZone: tz,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
    const parts = fmt.formatToParts(d);
    const get = (type: Intl.DateTimeFormatPartTypes) =>
      parts.find((p) => p.type === type)?.value ?? "00";
    return `${get("year")}-${get("month")}-${get("day")}T${get("hour")}:${get("minute")}`;
  } catch {
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
}

function statusBadge(task: ScheduledTask) {
  if (task.completed_at) return { text: "已完成", variant: "neutral" as const };
  if (!task.enabled) return { text: "已停用", variant: "neutral" as const };
  if (task.last_run_status === "running") return { text: "运行中", variant: "warning" as const };
  if (task.last_run_status === "failed") return { text: "上次失败", variant: "warning" as const };
  return { text: "等待中", variant: "success" as const };
}

function scheduleLabel(task: ScheduledTask, tz: string): string {
  if (task.schedule_kind === "once") {
    return task.run_at ? `单次 · ${formatWhen(task.run_at, tz)}` : "单次";
  }
  return `Cron · ${task.cron_expr ?? ""}`;
}

export function ScheduledTasksRoute() {
  const toast = useToast();
  const { confirm } = useDialogs();
  const [items, setItems] = useState<ScheduledTask[] | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [title, setTitle] = useState("");
  const [prompt, setPrompt] = useState("");
  const [scheduleKind, setScheduleKind] = useState<ScheduleKind>("cron");
  const [cronExpr, setCronExpr] = useState("0 9 * * *");
  const [runAt, setRunAt] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [notify, setNotify] = useState(true);
  const [busy, setBusy] = useState(false);
  const [userTimezone, setUserTimezone] = useState("UTC");
  const formRef = useRef<HTMLDivElement>(null);

  const load = async (silent = false) => {
    try {
      const [{ items }, tz] = await Promise.all([listScheduledTasks(), getTimezoneConfig()]);
      setItems(items);
      setUserTimezone(tz.timezone || "UTC");
    } catch (e) {
      if (!silent) toast((e as Error).message, "error");
      if (!silent) setItems([]);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const running = (items ?? []).some((t) => t.last_run_status === "running");
    if (!running) return;
    const id = window.setInterval(() => void load(true), 5000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items]);

  const reset = () => {
    setEditingId(null);
    setTitle("");
    setPrompt("");
    setScheduleKind("cron");
    setCronExpr("0 9 * * *");
    setRunAt("");
    setEnabled(true);
    setNotify(true);
  };

  const startEdit = (task: ScheduledTask) => {
    if (task.completed_at) return;
    setEditingId(task.id);
    setTitle(task.title);
    setPrompt(task.prompt);
    setScheduleKind(task.schedule_kind);
    setCronExpr(task.cron_expr ?? "0 9 * * *");
    setRunAt(toDatetimeLocal(task.run_at, userTimezone));
    setEnabled(task.enabled);
    setNotify(task.notify);
    requestAnimationFrame(() => formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };

  const submit = async () => {
    if (!title.trim() || !prompt.trim()) return;
    if (scheduleKind === "cron" && !cronExpr.trim()) return;
    if (scheduleKind === "once" && !runAt.trim()) return;
    setBusy(true);
    try {
      const body = {
        title: title.trim(),
        prompt: prompt.trim(),
        schedule_kind: scheduleKind,
        enabled,
        notify,
        cron_expr: scheduleKind === "cron" ? cronExpr.trim() : undefined,
        run_at: scheduleKind === "once" ? runAt.trim() : undefined,
      };
      if (editingId) {
        await updateScheduledTask(editingId, body);
        toast("已更新", "success");
      } else {
        await createScheduledTask(body);
        toast("已创建", "success");
      }
      reset();
      await load();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (task: ScheduledTask) => {
    if (!(await confirm({ title: "删除定时任务", body: `确定删除「${task.title}」？`, danger: true, confirmText: "删除" }))) return;
    setBusy(true);
    try {
      await deleteScheduledTask(task.id);
      if (editingId === task.id) reset();
      await load();
      toast("已删除", "success");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <PageContainer
      title="定时任务"
      subtitle="按 Cron 或指定时间自动运行 Agent；每次执行新建会话"
      actions={items ? <Badge variant="outline">共 {items.length} 条</Badge> : undefined}
    >
      <ReadyGate>
        <div className="space-y-4">
          {items === null ? (
            <Loading />
          ) : items.length === 0 ? (
            <Empty text="暂无定时任务" />
          ) : (
            <div className="space-y-2">
              {items.map((task) => {
                const st = statusBadge(task);
                return (
                  <ListCard key={task.id} className="p-0 overflow-hidden">
                    <div className="flex items-start gap-2 px-4 py-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-medium">{task.title}</span>
                          <Badge variant={st.variant}>{st.text}</Badge>
                          {task.notify ? <Badge variant="outline">通知</Badge> : null}
                        </div>
                        <p className="mt-1 text-xs text-muted-foreground">{scheduleLabel(task, userTimezone)}</p>
                        <p className="mt-0.5 text-xs text-muted-foreground">
                          下次执行：{formatWhen(task.next_run_at, userTimezone)}
                          {task.last_run_at ? ` · 上次：${formatWhen(task.last_run_at, userTimezone)}` : ""}
                        </p>
                        {task.last_error ? (
                          <p className="mt-1 text-xs text-destructive">{task.last_error}</p>
                        ) : null}
                        {task.last_session_id ? (
                          <Link
                            to={`/chat/${task.last_session_id}`}
                            className="mt-1 inline-block text-xs text-brand hover:underline"
                          >
                            查看上次会话
                          </Link>
                        ) : null}
                      </div>
                      <div className="flex shrink-0 items-center gap-1">
                        {!task.completed_at ? (
                          <>
                            <Button variant="ghost" size="icon-sm" disabled={busy} onClick={() => startEdit(task)}>
                              <Pencil className="size-3.5" />
                            </Button>
                          </>
                        ) : null}
                        <Button variant="ghost" size="icon-sm" disabled={busy} onClick={() => void remove(task)}>
                          <Trash2 className="size-3.5" />
                        </Button>
                      </div>
                    </div>
                    <CollapsibleSection summary="指令内容">
                      <pre className="whitespace-pre-wrap text-sm text-foreground">{task.prompt}</pre>
                    </CollapsibleSection>
                  </ListCard>
                );
              })}
            </div>
          )}

          <div ref={formRef}>
            <CollapsiblePanel
              summary={<span>{editingId ? "编辑任务" : "新建任务"}</span>}
              defaultOpen={!!editingId || items?.length === 0}
            >
              <div className="grid gap-3">
                <div className="grid gap-1.5">
                  <Label>标题</Label>
                  <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="例如：每日早报" />
                </div>
                <div className="grid gap-1.5">
                  <Label>指令（发给 Agent 的 prompt）</Label>
                  <Textarea
                    rows={5}
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    placeholder="到点后 Agent 将按此指令执行…"
                  />
                </div>
                <div className="grid gap-2">
                  <Label>类型</Label>
                  <div className="flex flex-wrap gap-2">
                    {(
                      [
                        ["cron", "重复（Cron）"],
                        ["once", "单次"],
                      ] as const
                    ).map(([kind, label]) => (
                      <button
                        key={kind}
                        type="button"
                        disabled={!!editingId}
                        onClick={() => setScheduleKind(kind)}
                        className={cn(
                          "rounded-lg border px-3 py-1.5 text-sm transition",
                          scheduleKind === kind
                            ? "border-brand bg-brand/10 text-foreground"
                            : "border-border text-muted-foreground hover:bg-surface",
                          editingId && "opacity-60",
                        )}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  {editingId ? (
                    <p className="text-xs text-muted-foreground">类型创建后不可修改</p>
                  ) : null}
                </div>
                {scheduleKind === "cron" ? (
                  <div className="grid gap-1.5">
                    <Label>Cron 选择器</Label>
                    <Cron
                      value={cronExpr}
                      setValue={(next: string) => setCronExpr(next || "")}
                      clearButton={false}
                      humanizeLabels
                      locale={CRON_LOCALE_ZH}
                    />
                    <p className="text-xs text-muted-foreground">
                      按设置中的时区解释。可视化选择后会自动生成 Cron 表达式。
                    </p>
                  </div>
                ) : (
                  <div className="grid gap-1.5">
                    <Label>执行时间</Label>
                    <Input
                      type="datetime-local"
                      step={300}
                      value={runAt}
                      onChange={(e) => setRunAt(e.target.value)}
                      className="max-w-sm"
                    />
                    <p className="text-xs text-muted-foreground">
                      按设置时区（{userTimezone}）填写，例如 2026-06-01 09:00
                    </p>
                  </div>
                )}
                <div className="flex flex-wrap gap-4">
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
                    启用
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={notify} onChange={(e) => setNotify(e.target.checked)} />
                    完成后通知（成功与失败）
                  </label>
                </div>
                <div className="flex gap-2">
                  <Button variant="primary" disabled={busy} onClick={() => void submit()}>
                    {busy && <Loader2 className="size-4 animate-spin" />}
                    {editingId ? "保存" : "创建"}
                  </Button>
                  {editingId ? (
                    <Button variant="secondary" disabled={busy} onClick={reset}>
                      取消
                    </Button>
                  ) : null}
                </div>
              </div>
            </CollapsiblePanel>
          </div>
        </div>
      </ReadyGate>
    </PageContainer>
  );
}
