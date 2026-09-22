import { useEffect, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import type { Trip, TripSuggestOut } from "@/lib/types";

const EXAMPLE_PROMPTS = [
  {
    label: "杭州3日",
    text: "帮我规划杭州3日游，2个人，喜欢历史和美食，预算不要太高",
  },
  {
    label: "重庆周末",
    text: "周末去重庆玩两天，2个人，想吃火锅、看夜景，节奏轻松一点",
  },
  {
    label: "亲子",
    text: "带孩子去上海玩3天，希望行程轻松、少排队，适合亲子",
  },
  {
    label: "美食向",
    text: "成都4日美食行程，2个人，想吃地道小吃，也留出逛街的时间",
  },
] as const;

const fieldClass =
  "w-full min-w-0 rounded-2xl border border-line-tertiary bg-white px-4 py-2.5 text-sm text-ink placeholder:text-ink-tertiary focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100";

const primaryButtonClass =
  "w-full rounded-full bg-blue-600 px-4 py-3 text-sm font-medium text-white transition hover:bg-blue-700 disabled:opacity-60";

const chipClass =
  "inline-flex items-center rounded-full border px-4 py-1.5 text-sm shadow-[inset_0_1px_0_rgba(255,255,255,0.9)] backdrop-blur-sm";

function messageFromError(err: unknown, fallback: string): string {
  const raw = err instanceof Error ? err.message.trim() : "";
  if (!raw || /提示词|API error/i.test(raw)) return fallback;
  return raw;
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block min-w-0">
      <span className="mb-1.5 block text-xs text-ink-tertiary">{label}</span>
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
  const [showDetails, setShowDetails] = useState(false);
  const [phase, setPhase] = useState<"idle" | "suggesting" | "creating">("idle");
  const [error, setError] = useState<string | null>(null);
  const busy = phase !== "idle";

  useEffect(() => {
    if (!suggestion) return;
    cardRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [suggestion]);

  useEffect(() => {
    if (!focusRequest.current) return;
    focusRequest.current = false;
    const field = textareaRef.current;
    if (!field) return;
    field.focus();
    const pos = field.value.length;
    field.setSelectionRange(pos, pos);
  }, [text]);

  function applyExample(example: string) {
    setError(null);
    setSuggestion(null);
    setSuggestedText(null);
    if (example === text) {
      textareaRef.current?.focus();
      return;
    }
    focusRequest.current = true;
    setText(example);
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
      setShowDetails(false);
    } catch (err) {
      setError(messageFromError(err, "暂时没能整理出行程，请稍后重试"));
    } finally {
      setPhase("idle");
    }
  }

  async function handleGenerate() {
    if (!destination.trim()) {
      setError("请填写目的地");
      return;
    }
    if (!startDate || !endDate) {
      setError("请填写出发和结束日期");
      return;
    }
    if (startDate > endDate) {
      setError("结束日期不能早于出发日期");
      return;
    }
    const count = Number(peopleCount);
    if (!Number.isInteger(count) || count < 1 || count > 20) {
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
      });
      navigate(`/trips/${trip.id}`);
    } catch (err) {
      setError(messageFromError(err, "行程还没生成成功，请稍后重试"));
      setPhase("idle");
    }
  }

  return (
    <div className="rounded-3xl border border-line-tertiary bg-white px-6 py-7 shadow-[0_1px_2px_rgba(20,20,20,0.04)] sm:px-8 sm:py-8">
      <div>
        <label htmlFor="trip-request" className="mb-3 block text-sm text-ink-secondary">
          用一句话描述你的旅行需求
        </label>
        <textarea
          id="trip-request"
          ref={textareaRef}
          value={text}
          onChange={(e) => {
            const next = e.target.value;
            setText(next);
            if (error) setError(null);
            if (suggestedText !== null && next.trim() !== suggestedText) {
              setSuggestion(null);
              setSuggestedText(null);
            }
          }}
          rows={4}
          placeholder="例如：帮我规划杭州3日游，2个人，喜欢历史和美食，预算不要太高"
          className={fieldClass}
        />
        <div className="mt-4 flex flex-wrap gap-2.5" role="group" aria-label="示例需求">
          {EXAMPLE_PROMPTS.map((example) => {
            const selected = text === example.text;
            return (
              <button
                key={example.label}
                type="button"
                onClick={() => applyExample(example.text)}
                disabled={busy}
                aria-pressed={selected}
                className={`${chipClass} transition disabled:opacity-60 ${
                  selected
                    ? "border-blue-600/40 bg-white text-blue-700"
                    : "border-line-tertiary bg-chrome/80 text-ink-secondary hover:bg-white/80 hover:text-ink"
                }`}
              >
                {example.label}
              </button>
            );
          })}
        </div>
      </div>

      {!suggestion && (
        <button
          type="button"
          onClick={handleSuggest}
          disabled={busy}
          className={`${primaryButtonClass} mt-6`}
        >
          {phase === "suggesting" ? "正在整理需求…" : "开始规划"}
        </button>
      )}

      {!suggestion && error && (
        <p className="mt-3 text-sm text-red-600" role="alert">
          {error}
        </p>
      )}

      {suggestion && (
        <div ref={cardRef} className="mt-8 border-t border-line-tertiary pt-8">
          <div className="mb-5 flex items-start justify-between gap-4">
            <div>
              <h2 className="text-base font-semibold text-ink">确认这些信息</h2>
              <p className="mt-1 text-sm text-ink-tertiary">改完后就可以生成行程</p>
            </div>
            <button
              type="button"
              onClick={handleSuggest}
              disabled={busy}
              className="shrink-0 text-sm text-ink-tertiary underline-offset-4 hover:text-ink-secondary hover:underline disabled:opacity-60"
            >
              {phase === "suggesting" ? "正在整理…" : "重新整理"}
            </button>
          </div>

          <div className="space-y-5">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="目的地">
                <input
                  value={destination}
                  onChange={(e) => setDestination(e.target.value)}
                  className={fieldClass}
                />
              </Field>
              <Field label="城市">
                <input
                  value={city}
                  onChange={(e) => setCity(e.target.value)}
                  placeholder="例如：杭州"
                  className={fieldClass}
                />
              </Field>
              <Field label="出发">
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className={fieldClass}
                />
              </Field>
              <Field label="结束">
                <input
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  className={fieldClass}
                />
              </Field>
              <Field label="人数">
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={peopleCount}
                  onChange={(e) => setPeopleCount(e.target.value)}
                  className={fieldClass}
                />
              </Field>
            </div>

            <div>
              <p className="mb-2.5 text-xs text-ink-tertiary">想去的地方</p>
              {mustVisit.length > 0 && (
                <ul className="mb-3 flex flex-wrap gap-2">
                  {mustVisit.map((place, index) => (
                    <li key={`${place}-${index}`}>
                      <span className={`${chipClass} gap-1.5 border-line-tertiary bg-chrome/80 text-ink`}>
                        {place}
                        <button
                          type="button"
                          aria-label={`移除${place}`}
                          onClick={() =>
                            setMustVisit((prev) => prev.filter((_, i) => i !== index))
                          }
                          className="text-ink-tertiary hover:text-ink"
                        >
                          ×
                        </button>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              <div className="flex gap-2">
                <input
                  value={mustVisitDraft}
                  onChange={(e) => setMustVisitDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      addMustVisit();
                    }
                  }}
                  placeholder="添加一个地方，回车确认"
                  className="min-w-0 flex-1 rounded-full border border-line-tertiary bg-white px-4 py-2.5 text-sm text-ink placeholder:text-ink-tertiary focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                />
                <button
                  type="button"
                  onClick={addMustVisit}
                  disabled={!mustVisitDraft.trim()}
                  className="shrink-0 rounded-full border border-line-tertiary bg-white/70 px-4 text-sm text-ink-secondary backdrop-blur-sm hover:text-ink disabled:opacity-40"
                >
                  添加
                </button>
              </div>
            </div>

            <div>
              <button
                type="button"
                aria-expanded={showDetails}
                onClick={() => setShowDetails((open) => !open)}
                className="text-sm text-ink-secondary underline-offset-4 hover:text-ink hover:underline"
              >
                {showDetails ? "收起详细需求" : "查看/编辑详细需求"}
              </button>
              {showDetails && (
                <div className="mt-2">
                  <textarea
                    value={optimizedPrompt}
                    onChange={(e) => setOptimizedPrompt(e.target.value)}
                    rows={3}
                    aria-label="详细需求"
                    className={fieldClass}
                  />
                  <p className="mt-1 text-xs text-ink-tertiary">
                    这段说明会一起用于生成行程，可以直接修改。
                  </p>
                </div>
              )}
            </div>

            {error && (
              <p className="text-sm text-red-600" role="alert">
                {error}
              </p>
            )}

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
