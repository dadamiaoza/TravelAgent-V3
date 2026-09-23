import { useEffect, useRef, useState, type ClipboardEvent, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import {
  detectDayCount,
  explicitDateRange,
  explicitPeople,
  guideFoldPreview,
  logisticsKind,
  looksLikeGuide,
} from "@/lib/guideInput";
import type { SourceDocument, SourceEntity, Trip, TripSuggestOut } from "@/lib/types";

const INSPIRATION_PROMPTS = [
  {
    label: "周末城市",
    text: "周末去重庆玩两天，2个人，想吃火锅、看夜景，节奏轻松一点",
  },
  {
    label: "美食出行",
    text: "成都4日美食行程，2个人，想吃地道小吃，也留出逛街的时间",
  },
  {
    label: "亲子轻松",
    text: "带孩子去上海玩3天，希望行程轻松、少排队，适合亲子",
  },
  {
    label: "城市漫步",
    text: "帮我规划杭州3日游，2个人，喜欢历史和美食，预算不要太高",
  },
  {
    label: "古迹慢游",
    text: "想去一座古城慢慢逛3天，2个人，喜欢历史街区和博物馆，每天别排太满",
  },
] as const;

const fieldClass =
  "w-full min-w-0 rounded-xl border border-line-tertiary bg-chrome px-4 py-2.5 text-sm text-ink placeholder:text-ink-tertiary focus:border-[rgb(20_20_20/0.16)] focus:outline-none";

const compactFieldClass =
  "h-9 w-full min-w-0 rounded-xl border border-line-tertiary bg-chrome px-3 text-sm text-ink placeholder:text-ink-tertiary focus:border-[rgb(20_20_20/0.16)] focus:outline-none";

const primaryButtonClass =
  "w-full rounded-full bg-blue-600 px-4 py-3 text-sm font-medium text-white transition hover:bg-blue-700 disabled:opacity-60";

const chipClass =
  "inline-flex items-center rounded-full border px-4 py-1.5 text-sm";

const confirmChipClass =
  "inline-flex shrink-0 items-center rounded-full border border-line-tertiary bg-chrome px-3 py-1 text-sm text-ink";

const formAlertClass =
  "mt-3 rounded-xl border border-line-tertiary bg-rose-50 px-3 py-2 text-sm text-rose-700";

function monthDay(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return "";
  return `${Number(match[2])}/${Number(match[3])}`;
}

function confirmSummary(input: {
  destination: string;
  city: string;
  start: string;
  end: string;
  people: string;
  dayCount: number | null;
  preferDayCount: boolean;
  showPeople: boolean;
}): string {
  const destination = input.destination.trim();
  const city = input.city.trim();
  const head =
    city && (!destination || destination.includes(city))
      ? city
      : destination || city || "目的地待定";
  const startLabel = monthDay(input.start);
  const endLabel = monthDay(input.end);
  const when =
    input.preferDayCount && input.dayCount
      ? `${input.dayCount}日`
      : startLabel && endLabel
        ? `${startLabel}–${endLabel}`
        : startLabel || endLabel || (input.dayCount ? `${input.dayCount}日` : "日期待定");
  const parts = [head, when];
  if (input.showPeople && input.people.trim()) parts.push(`${input.people.trim()}人`);
  return parts.join(" · ");
}

function localISODate(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function addDays(iso: string, days: number): string {
  const date = new Date(`${iso}T00:00:00`);
  date.setDate(date.getDate() + days);
  return localISODate(date);
}

function daysBetween(start: string, end: string): number | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end)) return null;
  const startMs = new Date(`${start}T00:00:00`).getTime();
  const endMs = new Date(`${end}T00:00:00`).getTime();
  if (Number.isNaN(startMs) || Number.isNaN(endMs)) return null;
  return Math.round((endMs - startMs) / 86_400_000);
}

const CHIP_LIMIT = 6;

function messageFromError(err: unknown, fallback: string): string {
  const raw = err instanceof Error ? err.message.trim() : "";
  if (!raw || /提示词|API error/i.test(raw)) return fallback;
  return raw;
}

function FormAlert({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className={formAlertClass}>
      {children}
    </p>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block min-w-0">
      <span className="mb-1 block text-xs text-ink-tertiary">{label}</span>
      {children}
    </label>
  );
}

export default function TripPromptForm() {
  const navigate = useNavigate();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const focusRequest = useRef(false);
  const [text, setText] = useState("");
  const [suggestedText, setSuggestedText] = useState<string | null>(null);
  const [suggestion, setSuggestion] = useState<TripSuggestOut | null>(null);
  const [destination, setDestination] = useState("");
  const [city, setCity] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [peopleCount, setPeopleCount] = useState("1");
  const [optimizedPrompt, setOptimizedPrompt] = useState("");
  const [mustVisit, setMustVisit] = useState<string[]>([]);
  const [mustVisitDraft, setMustVisitDraft] = useState("");
  const [editing, setEditing] = useState(false);
  const [inputMode, setInputMode] = useState<"sentence" | "guide">("sentence");
  const [guideHint, setGuideHint] = useState(false);
  const [foldPreview, setFoldPreview] = useState("");
  const [dayCount, setDayCount] = useState<number | null>(null);
  const [preferDayCount, setPreferDayCount] = useState(false);
  const [showPeople, setShowPeople] = useState(true);
  const [parsedEntities, setParsedEntities] = useState<SourceEntity[]>([]);
  const [phase, setPhase] = useState<"idle" | "suggesting" | "creating">("idle");
  const [error, setError] = useState<string | null>(null);
  const busy = phase !== "idle";

  useEffect(() => {
    if (!suggestion) return;
    const narrow = window.matchMedia("(max-width: 639px)").matches;
    cardRef.current?.scrollIntoView({
      behavior: "smooth",
      block: narrow && editing ? "start" : "nearest",
    });
  }, [suggestion, editing]);

  useEffect(() => {
    if (!focusRequest.current) return;
    focusRequest.current = false;
    const field = textareaRef.current;
    if (!field) return;
    field.focus();
    const pos = field.value.length;
    field.setSelectionRange(pos, pos);
  }, [text]);

  function writeInspiration(prompt: string) {
    setError(null);
    setSuggestion(null);
    setSuggestedText(null);
    const trimmed = text.trim();
    const untouchedPreset = INSPIRATION_PROMPTS.some((item) => item.text === trimmed);
    // Empty input, or a chip prompt the user has not edited: replace so switching inspirations stays clean.
    if (!trimmed || untouchedPreset) {
      if (text === prompt) {
        textareaRef.current?.focus();
        return;
      }
      focusRequest.current = true;
      setText(prompt);
      return;
    }
    // Keep what the user already wrote and append the prompt after a space.
    if (text.includes(prompt)) {
      textareaRef.current?.focus();
      return;
    }
    focusRequest.current = true;
    const spacer = /\s$/.test(text) ? "" : " ";
    setText(`${text}${spacer}${prompt}`);
  }

  function changeStartDate(nextStart: string) {
    setPreferDayCount(false);
    setStartDate(nextStart);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(nextStart)) return;
    if (dayCount != null && Number.isInteger(dayCount) && dayCount >= 1) {
      setEndDate(addDays(nextStart, dayCount - 1));
      return;
    }
    if (!startDate || !endDate) return;
    const span = daysBetween(startDate, endDate);
    if (span == null) return;
    setEndDate(addDays(nextStart, span));
  }

  function addMustVisit() {
    const name = mustVisitDraft.trim();
    if (!name) return;
    setMustVisit((prev) => (prev.includes(name) ? prev : [...prev, name]));
    setMustVisitDraft("");
  }

  async function handleSuggest() {
    const request = text.trim();
    if (!request) {
      setError("请先说说你想怎么玩");
      textareaRef.current?.focus();
      return;
    }
    setPhase("suggesting");
    setError(null);
    try {
      const result = await api.post<TripSuggestOut>("/trips/suggest", { text: request });
      setSuggestion(result);
      setSuggestedText(request);
      setCity(result.city ?? "");
      setDestination(result.destination ?? "");
      setStartDate(result.start_date ?? "");
      setEndDate(result.end_date ?? "");
      setPeopleCount(String(result.people_count ?? 1));
      setOptimizedPrompt(result.optimized_prompt ?? "");
      setMustVisit((result.must_visit ?? []).map((item) => item.trim()).filter(Boolean));
      setMustVisitDraft("");
      setParsedEntities([]);
      setDayCount(null);
      setPreferDayCount(false);
      setShowPeople(true);
      setFoldPreview(guideFoldPreview(result.optimized_prompt ?? ""));
      setEditing(false);
    } catch (err) {
      setError(messageFromError(err, "暂时没能整理出行程，请稍后重试"));
    } finally {
      setPhase("idle");
    }
  }

  async function handleGuide() {
    const request = text.trim();
    if (!request) {
      setError("请先粘贴攻略");
      textareaRef.current?.focus();
      return;
    }
    setPhase("suggesting");
    setError(null);
    try {
      const title = request.split("\n").map((line) => line.trim()).find(Boolean)?.slice(0, 30) || "攻略";
      const created = await api.post<SourceDocument>("/sources", { title, text: request });
      const parsed = await api.post<SourceDocument>(`/sources/${created.id}/parse`, {});
      const entities = parsed.entities ?? [];
      let destination = title;
      let city = "";
      const fromEntities = entities.length
        ? Math.max(...entities.map((item) => item.day_index || 1))
        : 1;
      let inferredDays = Math.max(detectDayCount(request) ?? 1, fromEntities);
      try {
        const inferred = await api.post<{ destination: string; city?: string | null; day_count: number }>(
          `/sources/${created.id}/infer-trip`,
          {},
        );
        destination = inferred.destination || destination;
        city = inferred.city ?? "";
        inferredDays = inferred.day_count || inferredDays;
      } catch {
        // Day marks and place names still fill the card when inference is unavailable.
      }
      const dated = explicitDateRange(request);
      const people = explicitPeople(request);
      const start = dated?.start ?? localISODate(new Date());
      const notes = entities
        .map((item) => item.visit_tips ?? "")
        .filter(Boolean);
      const visits = entities.filter((item) => !logisticsKind(item.poi_name));
      setSuggestion({
        destination,
        city,
        start_date: start,
        end_date: dated?.end ?? addDays(start, Math.max(inferredDays, 1) - 1),
        people_count: people ?? 1,
        optimized_prompt: request,
        must_visit: visits.map((item) => item.poi_name),
      });
      setSuggestedText(request);
      setDestination(destination);
      setCity(city);
      setStartDate(start);
      setEndDate(dated?.end ?? addDays(start, Math.max(inferredDays, 1) - 1));
      setPeopleCount(String(people ?? 1));
      setOptimizedPrompt(request);
      setMustVisit(visits.map((item) => item.poi_name.trim()).filter(Boolean));
      setMustVisitDraft("");
      setParsedEntities(entities);
      setDayCount(inferredDays);
      setPreferDayCount(!dated);
      setShowPeople(people !== null);
      setFoldPreview(guideFoldPreview(request, notes));
      setEditing(false);
    } catch (err) {
      setError(messageFromError(err, "暂时没能解析这篇攻略，请稍后重试"));
    } finally {
      setPhase("idle");
    }
  }

  function handlePrimary() {
    if (inputMode === "guide") {
      void handleGuide();
      return;
    }
    void handleSuggest();
  }

  function chooseMode(next: "sentence" | "guide") {
    if (next === inputMode) return;
    setInputMode(next);
    setGuideHint(false);
    setSuggestion(null);
    setSuggestedText(null);
    setError(null);
  }

  function handlePaste(event: ClipboardEvent<HTMLTextAreaElement>) {
    const pasted = event.clipboardData.getData("text");
    const field = event.currentTarget;
    const start = field.selectionStart ?? field.value.length;
    const end = field.selectionEnd ?? field.value.length;
    const next = `${field.value.slice(0, start)}${pasted}${field.value.slice(end)}`;
    if (inputMode === "sentence" && looksLikeGuide(next)) {
      setInputMode("guide");
      setGuideHint(true);
    }
  }

  async function handleGenerate() {
    if (!destination.trim()) {
      setEditing(true);
      setError("请填写目的地");
      return;
    }
    if (!startDate || !endDate) {
      setEditing(true);
      setError("请填写出发和结束日期");
      return;
    }
    if (startDate > endDate) {
      setEditing(true);
      setError("结束日期不能早于出发日期");
      return;
    }
    const count = Number(peopleCount);
    if (!Number.isInteger(count) || count < 1 || count > 20) {
      setEditing(true);
      setError("人数需要是 1 到 20 人");
      return;
    }

    setPhase("creating");
    setError(null);
    try {
      const trip = await api.post<Trip>("/trips", {
        destination: destination.trim(),
        city: city.trim() || undefined,
        start_date: startDate,
        end_date: endDate,
        people_count: count,
        user_prompt: optimizedPrompt.trim() || undefined,
        must_visit: mustVisit,
        ...(parsedEntities.length > 0
          ? {
              selected_entities: parsedEntities.map((entity) => ({
                poi_name: entity.poi_name,
                day_index: entity.day_index,
                seq: entity.seq,
                lat: entity.lat ?? null,
                lng: entity.lng ?? null,
                suggested_duration_h: entity.suggested_duration_h ?? null,
                best_time: entity.best_time ?? null,
                cost_estimate: entity.cost_estimate ?? null,
                visit_tips: entity.visit_tips ?? null,
              })),
            }
          : {}),
      });
      navigate(`/trips/${trip.id}`);
    } catch (err) {
      setError(messageFromError(err, "行程还没生成成功，请稍后重试"));
      setPhase("idle");
    }
  }

  const summary = confirmSummary({
    destination,
    city,
    start: startDate,
    end: endDate,
    people: peopleCount,
    dayCount,
    preferDayCount,
    showPeople,
  });
  const rerunLabel = phase === "suggesting"
    ? inputMode === "guide"
      ? "正在解析…"
      : "正在整理…"
    : "重新整理";
  const visiblePlaces = mustVisit.slice(0, CHIP_LIMIT);
  const hiddenPlaceCount = Math.max(0, mustVisit.length - CHIP_LIMIT);
  const modeChip = (selected: boolean) =>
    `${chipClass} transition disabled:opacity-60 ${
      selected
        ? "border-blue-600/40 bg-elevated text-blue-700 shadow-sm"
        : "border-line-tertiary bg-chrome text-ink-secondary hover:text-ink"
    }`;

  return (
    <div className="rounded-2xl border border-line-tertiary bg-elevated px-6 py-7 shadow-sm sm:px-8 sm:py-8">
      <div>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <label htmlFor="trip-request" className="text-sm text-ink-secondary">
            {inputMode === "guide" ? "粘贴一篇攻略" : "用一句话描述你的旅行需求"}
          </label>
          <div className="flex gap-2" role="group" aria-label="输入方式">
            <button
              type="button"
              aria-pressed={inputMode === "sentence"}
              onClick={() => chooseMode("sentence")}
              className={modeChip(inputMode === "sentence")}
            >
              一句话
            </button>
            <button
              type="button"
              aria-pressed={inputMode === "guide"}
              onClick={() => chooseMode("guide")}
              className={modeChip(inputMode === "guide")}
            >
              粘贴攻略
            </button>
          </div>
        </div>
        <textarea
          id="trip-request"
          ref={textareaRef}
          value={text}
          onPaste={handlePaste}
          onChange={(e) => {
            const next = e.target.value;
            setText(next);
            if (error) setError(null);
            if (suggestedText !== null && next.trim() !== suggestedText) {
              setSuggestion(null);
              setSuggestedText(null);
            }
          }}
          rows={inputMode === "guide" ? 8 : 4}
          placeholder={
            inputMode === "guide"
              ? "例如：长沙3日。交通：长沙南。D1 五一广场 → 坡子街。住：五一/芙蓉。Tips：省博提前约"
              : "例如：帮我规划杭州3日游，2个人，喜欢历史和美食，预算不要太高"
          }
          className={fieldClass}
        />
        {guideHint && inputMode === "guide" && (
          <p className="mt-2 text-xs text-ink-tertiary">看起来像攻略，将按攻略解析</p>
        )}
        {inputMode === "sentence" && (
          <div className="mt-4">
            <p className="mb-2 text-xs text-ink-tertiary">灵感</p>
            <div className="flex flex-wrap gap-2.5" role="group" aria-label="旅行灵感">
              {INSPIRATION_PROMPTS.map((example) => {
                const selected = text.trim() === example.text;
                return (
                  <button
                    key={example.label}
                    type="button"
                    onClick={() => writeInspiration(example.text)}
                    disabled={busy}
                    aria-pressed={selected}
                    className={`${chipClass} transition disabled:opacity-60 ${
                      selected
                        ? "border-blue-600/40 bg-elevated text-blue-700 shadow-sm"
                        : "border-line-tertiary bg-chrome text-ink-secondary hover:text-ink"
                    }`}
                  >
                    {example.label}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {!suggestion && (
        <button
          type="button"
          onClick={handlePrimary}
          disabled={busy}
          className={`${primaryButtonClass} mt-6`}
        >
          {phase === "suggesting"
            ? inputMode === "guide"
              ? "正在解析攻略…"
              : "正在整理需求…"
            : inputMode === "guide"
              ? "解析并规划"
              : "开始规划"}
        </button>
      )}

      {!suggestion && error && <FormAlert>{error}</FormAlert>}

      {suggestion && (
        <div
          ref={cardRef}
          className={`mt-6 border-t border-line-tertiary pt-5 ${
            editing
              ? "max-sm:sticky max-sm:top-2 max-sm:z-10 max-sm:flex max-sm:max-h-[calc(100dvh-1rem)] max-sm:min-h-0 max-sm:flex-col max-sm:overflow-hidden"
              : ""
          }`}
        >
          <div className={editing ? "max-sm:min-h-0 max-sm:flex-1 max-sm:overflow-y-auto max-sm:overscroll-contain max-sm:pb-6" : undefined}>
          {editing ? (
            <div className="space-y-3">
              <div className="flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={handlePrimary}
                  disabled={busy}
                  className="text-sm text-ink-tertiary hover:text-ink-secondary disabled:opacity-60"
                >
                  {rerunLabel}
                </button>
                <button
                  type="button"
                  aria-expanded={editing}
                  onClick={() => setEditing(false)}
                  className="text-sm font-medium text-blue-700"
                >
                  收起
                </button>
              </div>
              <div className="grid grid-cols-1 gap-y-2 sm:grid-cols-2 sm:gap-x-3">
                <Field label="目的地">
                  <input
                    value={destination}
                    onChange={(e) => setDestination(e.target.value)}
                    className={compactFieldClass}
                  />
                </Field>
                <Field label="城市">
                  <input
                    value={city}
                    onChange={(e) => setCity(e.target.value)}
                    placeholder="例如：杭州"
                    className={compactFieldClass}
                  />
                </Field>
                <Field label="出发">
                  <input
                    type="date"
                    value={startDate}
                    onChange={(e) => changeStartDate(e.target.value)}
                    className={compactFieldClass}
                  />
                </Field>
                <Field label="结束">
                  <input
                    type="date"
                    value={endDate}
                    onChange={(e) => {
                      setPreferDayCount(false);
                      setEndDate(e.target.value);
                    }}
                    className={compactFieldClass}
                  />
                </Field>
                <Field label="人数">
                  <input
                    type="number"
                    min={1}
                    max={20}
                    value={peopleCount}
                    onChange={(e) => {
                      setShowPeople(true);
                      setPeopleCount(e.target.value);
                    }}
                    className={compactFieldClass}
                  />
                </Field>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                {mustVisit.map((place, index) => (
                  <span
                    key={`${place}-${index}`}
                    className={`${confirmChipClass} gap-1`}
                  >
                    {place}
                    <button
                      type="button"
                      aria-label={`移除${place}`}
                      onClick={() => setMustVisit((prev) => prev.filter((_, i) => i !== index))}
                      className="text-ink-tertiary hover:text-ink"
                    >
                      ×
                    </button>
                  </span>
                ))}
                <input
                  value={mustVisitDraft}
                  onChange={(e) => setMustVisitDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      addMustVisit();
                    }
                  }}
                  placeholder="添加地点"
                  aria-label="添加想去的地方"
                  className="h-8 w-28 min-w-0 rounded-full border border-line-tertiary bg-chrome px-3 text-sm text-ink placeholder:text-ink-tertiary focus:border-[rgb(20_20_20/0.16)] focus:outline-none"
                />
              </div>
              <textarea
                value={optimizedPrompt}
                onChange={(e) => setOptimizedPrompt(e.target.value)}
                rows={4}
                aria-label="完整需求"
                className="w-full rounded-xl border border-line-tertiary bg-chrome px-3 py-2 text-sm text-ink focus:border-[rgb(20_20_20/0.16)] focus:outline-none"
              />
            </div>
          ) : (
            <div>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => setEditing(true)}
                  className="min-w-0 flex-1 truncate text-left text-sm font-medium text-ink"
                >
                  {summary}
                </button>
                <button
                  type="button"
                  onClick={handlePrimary}
                  disabled={busy}
                  className="shrink-0 text-sm text-ink-tertiary hover:text-ink-secondary disabled:opacity-60"
                >
                  {rerunLabel}
                </button>
                <button
                  type="button"
                  aria-expanded={editing}
                  onClick={() => setEditing(true)}
                  className="shrink-0 text-sm font-medium text-blue-700"
                >
                  修改
                </button>
              </div>
              {mustVisit.length > 0 && (
                <ul className="mt-2 flex gap-1.5 overflow-x-auto">
                  {visiblePlaces.map((place, index) => (
                    <li key={`${place}-${index}`} className="shrink-0">
                      <span className={confirmChipClass}>{place}</span>
                    </li>
                  ))}
                  {hiddenPlaceCount > 0 && (
                    <li className="shrink-0">
                      <button
                        type="button"
                        onClick={() => setEditing(true)}
                        className={`${confirmChipClass} text-ink-secondary`}
                      >
                        +{hiddenPlaceCount}
                      </button>
                    </li>
                  )}
                </ul>
              )}
              {foldPreview && (
                <button
                  type="button"
                  onClick={() => setEditing(true)}
                  className="mt-2 flex w-full min-w-0 items-center gap-3 text-left"
                >
                  <span className="min-w-0 flex-1 truncate text-sm text-ink-secondary">{foldPreview}</span>
                  <span className="shrink-0 text-sm text-ink-tertiary">查看完整需求</span>
                </button>
              )}
            </div>
          )}

          {error && <FormAlert>{error}</FormAlert>}
          </div>

          <div
            className={
              editing
                ? "max-sm:shrink-0 max-sm:border-t max-sm:border-line-tertiary max-sm:bg-elevated max-sm:pt-3 sm:mt-3"
                : "mt-3"
            }
          >
            <button
              type="button"
              onClick={handleGenerate}
              disabled={busy}
              className={primaryButtonClass}
            >
              {phase === "creating" ? "正在生成行程…" : "确认并生成行程"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
