import { useEffect, useMemo, useRef, useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight, Loader2, Pencil, Play, Trash2 } from "lucide-react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { Cron, type Locale as CronLocale } from "react-js-cron";
import "react-js-cron/styles.css";
import { PageContainer } from "@/components/PageContainer";
import { ReadyGate } from "@/components/ReadyGate";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label, Select, Textarea } from "@/components/ui/field";
import { CollapsiblePanel, CollapsibleSection, ListCard } from "@/components/ui/panel";
import { SegmentControl } from "@/components/ui/segment-control";
import { Empty, listItemBriefClass, listRowHoverActionsClass, Loading } from "@/components/ui/list-state";
import { useDialogs } from "@/components/ui/dialogs";
import { useToast } from "@/components/ui/toast";
import {
  createScheduledTask,
  deleteScheduledTask,
  listScheduledTasks,
  runScheduledTaskNow,
  updateScheduledTask,
} from "@/api/endpoints";
import type { ScheduledTask, ScheduleKind } from "@/api/types";
import { cn } from "@/lib/utils";
import { toastAction } from "@/lib/toast-copy";
import { useTimeFormatters } from "@/lib/use-app-timezone";

function buildCronLocale(t: TFunction): CronLocale {
  return {
    everyText: t("scheduled.cron.everyText"),
    emptyMonths: t("scheduled.cron.emptyMonths"),
    emptyMonthDays: t("scheduled.cron.emptyMonthDays"),
    emptyMonthDaysShort: t("scheduled.cron.emptyMonthDaysShort"),
    emptyWeekDays: t("scheduled.cron.emptyWeekDays"),
    emptyWeekDaysShort: t("scheduled.cron.emptyWeekDaysShort"),
    emptyHours: t("scheduled.cron.emptyHours"),
    emptyMinutes: t("scheduled.cron.emptyMinutes"),
    emptyMinutesForHourPeriod: t("scheduled.cron.emptyMinutesForHourPeriod"),
    yearOption: t("scheduled.cron.yearOption"),
    monthOption: t("scheduled.cron.monthOption"),
    weekOption: t("scheduled.cron.weekOption"),
    dayOption: t("scheduled.cron.dayOption"),
    hourOption: t("scheduled.cron.hourOption"),
    minuteOption: t("scheduled.cron.minuteOption"),
    rebootOption: t("scheduled.cron.rebootOption"),
    prefixPeriod: t("scheduled.cron.prefixPeriod"),
    prefixMonths: t("scheduled.cron.prefixMonths"),
    prefixMonthDays: t("scheduled.cron.prefixMonthDays"),
    prefixWeekDays: t("scheduled.cron.prefixWeekDays"),
    prefixWeekDaysForMonthAndYearPeriod: t("scheduled.cron.prefixWeekDaysForMonthAndYearPeriod"),
    prefixHours: t("scheduled.cron.prefixHours"),
    prefixMinutes: t("scheduled.cron.prefixMinutes"),
    prefixMinutesForHourPeriod: t("scheduled.cron.prefixMinutesForHourPeriod"),
    suffixMinutesForHourPeriod: t("scheduled.cron.suffixMinutesForHourPeriod"),
    errorInvalidCron: t("scheduled.cron.errorInvalidCron"),
    clearButtonText: t("scheduled.cron.clearButtonText"),
    weekDays: t("scheduled.cron.weekDays", { returnObjects: true }) as string[],
    months: t("scheduled.cron.months", { returnObjects: true }) as string[],
    altWeekDays: t("scheduled.cron.altWeekDays", { returnObjects: true }) as string[],
    altMonths: t("scheduled.cron.altMonths", { returnObjects: true }) as string[],
  };
}

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

function parseDateTimeLocal(value: string): { y: number; m: number; d: number; hh: number; mm: number } | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value.trim());
  if (!m) return null;
  return {
    y: Number(m[1]),
    m: Number(m[2]),
    d: Number(m[3]),
    hh: Number(m[4]),
    mm: Number(m[5]),
  };
}

function formatDateTimeLocal(parts: { y: number; m: number; d: number; hh: number; mm: number }): string {
  return `${parts.y}-${pad2(parts.m)}-${pad2(parts.d)}T${pad2(parts.hh)}:${pad2(parts.mm)}`;
}

function daysInMonth(year: number, month: number): number {
  return new Date(year, month, 0).getDate();
}

function DateTimePicker({
  value,
  onChange,
}: {
  value: string;
  onChange: (next: string) => void;
}) {
  const { t } = useTranslation();
  const weekdays = t("scheduled.datetimePicker.weekdays", { returnObjects: true }) as string[];
  const now = new Date();
  const parsed = parseDateTimeLocal(value);
  const [open, setOpen] = useState(false);
  const [viewY, setViewY] = useState(parsed?.y ?? now.getFullYear());
  const [viewM, setViewM] = useState(parsed?.m ?? now.getMonth() + 1);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const p = parseDateTimeLocal(value);
    if (p) {
      setViewY(p.y);
      setViewM(p.m);
    }
  }, [open, value]);

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      const t = e.target as Node | null;
      if (!t) return;
      if (rootRef.current?.contains(t)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  const shiftMonth = (delta: number) => {
    const d = new Date(viewY, viewM - 1 + delta, 1);
    setViewY(d.getFullYear());
    setViewM(d.getMonth() + 1);
  };

  const firstWeekday = new Date(viewY, viewM - 1, 1).getDay();
  const totalDays = daysInMonth(viewY, viewM);
  const selected = parsed;

  const applyDate = (day: number) => {
    const base = selected ?? { y: viewY, m: viewM, d: day, hh: 9, mm: 0 };
    onChange(formatDateTimeLocal({ ...base, y: viewY, m: viewM, d: day }));
  };

  const applyTime = (nextHour: number | null, nextMinute: number | null) => {
    const base = selected ?? { y: viewY, m: viewM, d: 1, hh: 9, mm: 0 };
    onChange(
      formatDateTimeLocal({
        ...base,
        hh: nextHour ?? base.hh,
        mm: nextMinute ?? base.mm,
      }),
    );
  };

  const display = selected
    ? `${selected.y}-${pad2(selected.m)}-${pad2(selected.d)} ${pad2(selected.hh)}:${pad2(selected.mm)}`
    : "";

  return (
    <div ref={rootRef} className="relative max-w-sm">
      <Input
        readOnly
        value={display}
        onClick={() => setOpen((v) => !v)}
        placeholder={t("scheduled.datetimePicker.placeholder")}
        className="cursor-pointer pr-10"
      />
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="absolute right-1 top-1/2 inline-flex size-7 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground hover:bg-secondary"
        aria-label={t("scheduled.datetimePicker.openCalendar")}
      >
        <CalendarDays className="size-4" />
      </button>
      {open ? (
        <ListCard className="absolute bottom-full left-0 z-20 mb-2 w-[320px] overflow-hidden p-0 shadow-lg bg-surface!">
          <div className="flex items-center justify-between px-4 py-3">
            <Button variant="ghost" size="icon-sm" onClick={() => shiftMonth(-1)} aria-label={t("scheduled.datetimePicker.prevMonth")}>
              <ChevronLeft className="size-4" />
            </Button>
            <span className="text-sm font-medium">
              {t("scheduled.datetimePicker.yearMonth", { year: viewY, month: viewM })}
            </span>
            <Button variant="ghost" size="icon-sm" onClick={() => shiftMonth(1)} aria-label={t("scheduled.datetimePicker.nextMonth")}>
              <ChevronRight className="size-4" />
            </Button>
          </div>
          <div className="grid grid-cols-7 gap-1 px-4 pb-1 text-center text-xs text-muted-foreground">
            {weekdays.map((w) => (
              <span key={w}>{w}</span>
            ))}
          </div>
          <div className="grid grid-cols-7 gap-1 px-4 pb-3">
            {Array.from({ length: firstWeekday }).map((_, i) => (
              <span key={`e-${i}`} />
            ))}
            {Array.from({ length: totalDays }).map((_, i) => {
              const day = i + 1;
              const isActive = !!selected && selected.y === viewY && selected.m === viewM && selected.d === day;
              return (
                <button
                  key={day}
                  type="button"
                  onClick={() => applyDate(day)}
                  className={cn(
                    "h-8 rounded-md text-sm transition",
                    isActive ? "bg-brand text-brand-foreground" : "hover:bg-secondary text-foreground",
                  )}
                >
                  {day}
                </button>
              );
            })}
          </div>
          <div className="grid gap-3 px-4 pb-3">
            <div className="grid grid-cols-2 gap-2">
              <div className="grid gap-1">
                <Label>{t("scheduled.datetimePicker.hour")}</Label>
                <Select
                  value={String(selected?.hh ?? 9)}
                  onChange={(e) => applyTime(Number(e.target.value), null)}
                >
                  {Array.from({ length: 24 }).map((_, h) => (
                    <option key={h} value={h}>
                      {pad2(h)}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="grid gap-1">
                <Label>{t("scheduled.datetimePicker.minute")}</Label>
                <Select
                  value={String(selected?.mm ?? 0)}
                  onChange={(e) => applyTime(null, Number(e.target.value))}
                >
                  {Array.from({ length: 12 }).map((_, i) => {
                    const m = i * 5;
                    return (
                      <option key={m} value={m}>
                        {pad2(m)}
                      </option>
                    );
                  })}
                </Select>
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={() => onChange("")}>
                {t("scheduled.datetimePicker.clear")}
              </Button>
              <Button variant="secondary" size="sm" onClick={() => setOpen(false)}>
                {t("scheduled.datetimePicker.done")}
              </Button>
            </div>
          </div>
        </ListCard>
      ) : null}
    </div>
  );
}

function statusBadge(task: ScheduledTask, t: TFunction) {
  if (task.completed_at) return { text: t("scheduled.status.completed"), variant: "neutral" as const };
  if (task.last_run_status === "running") return { text: t("scheduled.status.running"), variant: "warning" as const };
  if (task.last_run_status === "queued") return { text: t("scheduled.status.queued"), variant: "warning" as const };
  if (!task.enabled) return { text: t("scheduled.status.disabled"), variant: "neutral" as const };
  if (task.last_run_status === "failed") return { text: t("scheduled.status.failed"), variant: "warning" as const };
  return { text: t("scheduled.status.waiting"), variant: "success" as const };
}

function isTaskBusy(task: ScheduledTask, pendingRunIds: ReadonlySet<number>): boolean {
  return (
    pendingRunIds.has(task.id) ||
    task.last_run_status === "running" ||
    task.last_run_status === "queued"
  );
}

function scheduleLabel(
  task: ScheduledTask,
  formatDt: (iso: string | null | undefined) => string,
  t: TFunction,
): string {
  if (task.schedule_kind === "once") {
    return task.run_at
      ? t("scheduled.type.onceAt", { time: formatDt(task.run_at) })
      : t("scheduled.type.once");
  }
  return t("scheduled.type.cron", { expr: task.cron_expr ?? "" });
}

export function ScheduledTasksRoute() {
  const { t, i18n } = useTranslation();
  const cronLocale = useMemo(() => buildCronLocale(t), [t, i18n.language]);
  const toast = useToast();
  const { confirm } = useDialogs();
  const { timeZone, formatDateTime, toDatetimeLocal } = useTimeFormatters();
  const [items, setItems] = useState<ScheduledTask[] | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [title, setTitle] = useState("");
  const [prompt, setPrompt] = useState("");
  const [scheduleKind, setScheduleKind] = useState<ScheduleKind>("cron");
  const [cronExpr, setCronExpr] = useState("0 9 * * *");
  const [runAt, setRunAt] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [notify, setNotify] = useState(true);
  const [saving, setSaving] = useState(false);
  const [pendingRunIds, setPendingRunIds] = useState<Set<number>>(() => new Set());
  const formRef = useRef<HTMLDivElement>(null);

  const load = async (silent = false) => {
    try {
      const { items } = await listScheduledTasks();
      setItems(items);
    } catch (e) {
      if (!silent) toast((e as Error).message, "error");
      if (!silent) setItems([]);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    const running = (items ?? []).some(
      (t) => t.last_run_status === "running" || t.last_run_status === "queued",
    );
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
    if (task.completed_at || isTaskBusy(task, pendingRunIds)) return;
    setEditingId(task.id);
    setTitle(task.title);
    setPrompt(task.prompt);
    setScheduleKind(task.schedule_kind);
    setCronExpr(task.cron_expr ?? "0 9 * * *");
    setRunAt(toDatetimeLocal(task.run_at));
    setEnabled(task.enabled);
    setNotify(task.notify);
    requestAnimationFrame(() => formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };

  const submit = async () => {
    if (!title.trim()) {
      toast(t("scheduled.validation.title"), "error");
      return;
    }
    if (!prompt.trim()) {
      toast(t("scheduled.validation.instruction"), "error");
      return;
    }
    if (scheduleKind === "cron" && !cronExpr.trim()) {
      toast(t("scheduled.validation.cron"), "error");
      return;
    }
    if (scheduleKind === "once" && !runAt.trim()) {
      toast(t("scheduled.validation.runAt"), "error");
      return;
    }
    setSaving(true);
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
        toast(toastAction("updated", title.trim(), "scheduledTask"), "success");
      } else {
        await createScheduledTask(body);
        toast(toastAction("added", title.trim(), "scheduledTask"), "success");
      }
      reset();
      await load();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSaving(false);
    }
  };

  const runOnce = async (task: ScheduledTask) => {
    if (isTaskBusy(task, pendingRunIds)) return;
    setPendingRunIds((prev) => new Set(prev).add(task.id));
    setSaving(true);
    try {
      await runScheduledTaskNow(task.id);
      toast(toastAction("started", task.title, "scheduledTask"), "success");
      await load();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setPendingRunIds((prev) => {
        const next = new Set(prev);
        next.delete(task.id);
        return next;
      });
      setSaving(false);
    }
  };

  const remove = async (task: ScheduledTask) => {
    if (isTaskBusy(task, pendingRunIds)) return;
    if (
      !(await confirm({
        title: t("scheduled.form.deleteTitle"),
        body: t("scheduled.form.deleteBody", { title: task.title }),
        danger: true,
        confirmText: t("common.actions.delete"),
      }))
    )
      return;
    setSaving(true);
    try {
      await deleteScheduledTask(task.id);
      if (editingId === task.id) reset();
      await load();
      toast(toastAction("deleted", task.title, "scheduledTask"), "success");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <PageContainer
      title={t("scheduled.title")}
      subtitle={t("scheduled.subtitle")}
      actions={items ? <Badge variant="outline">{t("scheduled.count", { count: items.length })}</Badge> : undefined}
    >
      <ReadyGate>
        <div className="space-y-4">
          {items === null ? (
            <Loading />
          ) : items.length === 0 ? (
            <Empty text={t("scheduled.empty")} />
          ) : (
            <div className="space-y-2">
              {items.map((task) => {
                const st = statusBadge(task, t);
                return (
                  <ListCard key={task.id} className="group p-0 overflow-hidden">
                    <div className="flex items-start gap-2 px-4 py-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-medium">{task.title}</span>
                          <Badge variant={st.variant}>{st.text}</Badge>
                          {task.notify ? <Badge variant="outline">{t("scheduled.notifyBadge")}</Badge> : null}
                        </div>
                        <p className={listItemBriefClass}>{scheduleLabel(task, formatDateTime, t)}</p>
                        <p className={listItemBriefClass}>
                          {t("scheduled.runSchedule.next")}{formatDateTime(task.next_run_at)}
                          {task.last_run_at
                            ? ` · ${t("scheduled.runSchedule.last")}${formatDateTime(task.last_run_at)}`
                            : ""}
                        </p>
                        {task.last_error ? (
                          <p className="mt-1 text-xs text-destructive">{task.last_error}</p>
                        ) : null}
                      </div>
                      <div className="flex shrink-0 items-center gap-1">
                        {!task.completed_at ? (
                          <>
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              className={listRowHoverActionsClass}
                              disabled={saving || isTaskBusy(task, pendingRunIds)}
                              onClick={() => void runOnce(task)}
                              aria-label={t("scheduled.actions.runOnce")}
                              title={t("scheduled.actions.runOnce")}
                            >
                              <Play />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              className={listRowHoverActionsClass}
                              disabled={saving || isTaskBusy(task, pendingRunIds)}
                              onClick={() => startEdit(task)}
                              aria-label={t("common.actions.edit")}
                              title={t("common.actions.edit")}
                            >
                              <Pencil />
                            </Button>
                          </>
                        ) : null}
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          className={listRowHoverActionsClass}
                          disabled={saving || isTaskBusy(task, pendingRunIds)}
                          onClick={() => void remove(task)}
                          aria-label={t("common.actions.delete")}
                          title={t("common.actions.delete")}
                        >
                          <Trash2 />
                        </Button>
                      </div>
                    </div>
                    <CollapsibleSection summary={t("scheduled.actions.instruction")}>
                      <pre className="whitespace-pre-wrap text-sm text-foreground">{task.prompt}</pre>
                    </CollapsibleSection>
                    {task.last_run_summary ? (
                      <CollapsibleSection summary={t("scheduled.actions.lastResult")}>
                        <pre className="whitespace-pre-wrap text-sm text-foreground">{task.last_run_summary}</pre>
                      </CollapsibleSection>
                    ) : null}
                  </ListCard>
                );
              })}
            </div>
          )}

          <div ref={formRef}>
            <CollapsiblePanel
              summary={<span>{editingId ? t("scheduled.form.editTitle") : t("scheduled.form.createTitle")}</span>}
              defaultOpen={!!editingId || items?.length === 0}
              onOpenChange={(open) => {
                if (!open) reset();
              }}
            >
              <div className="grid gap-3">
                <div className="grid gap-1.5">
                  <Label>{t("scheduled.form.title")}</Label>
                  <Input
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder={t("scheduled.form.titlePlaceholder")}
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label>{t("scheduled.form.instruction")}</Label>
                  <Textarea
                    rows={5}
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    placeholder={t("scheduled.form.instructionPlaceholder")}
                  />
                </div>
                <div className="grid gap-2">
                  <Label>{t("scheduled.form.type")}</Label>
                  <SegmentControl
                    value={scheduleKind}
                    onChange={setScheduleKind}
                    options={[
                      { value: "cron", label: t("scheduled.form.typeCron"), disabled: !!editingId },
                      { value: "once", label: t("scheduled.form.typeOnce"), disabled: !!editingId },
                    ]}
                    className={cn(editingId && "opacity-60")}
                  />
                  {editingId ? (
                    <p className="text-xs text-muted-foreground">{t("scheduled.form.typeImmutable")}</p>
                  ) : null}
                </div>
                {scheduleKind === "cron" ? (
                  <div className="grid gap-1.5">
                    <Label>{t("scheduled.form.cronPicker")}</Label>
                    <Cron
                      value={cronExpr}
                      setValue={(next: string) => setCronExpr(next || "")}
                      clearButton={false}
                      humanizeLabels
                      locale={cronLocale}
                    />
                    <p className="text-xs text-muted-foreground">{t("scheduled.form.cronHint")}</p>
                  </div>
                ) : (
                  <div className="grid gap-1.5">
                    <Label>{t("scheduled.form.runAt")}</Label>
                    <DateTimePicker value={runAt} onChange={setRunAt} />
                    <p className="text-xs text-muted-foreground">
                      {t("scheduled.form.runAtHint", { timeZone })}
                    </p>
                  </div>
                )}
                <div className="flex flex-wrap gap-4">
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
                    {t("scheduled.form.enabled")}
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={notify} onChange={(e) => setNotify(e.target.checked)} />
                    {t("scheduled.form.notify")}
                  </label>
                </div>
                <div className="flex gap-2">
                  <Button variant="primary" disabled={saving} onClick={() => void submit()}>
                    {saving && <Loader2 className="size-4 animate-spin" />}
                    {editingId ? t("common.actions.save") : t("common.actions.add")}
                  </Button>
                </div>
              </div>
            </CollapsiblePanel>
          </div>
        </div>
      </ReadyGate>
    </PageContainer>
  );
}
